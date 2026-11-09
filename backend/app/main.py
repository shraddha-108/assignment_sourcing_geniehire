import logging
import uuid
from contextlib import asynccontextmanager
from copy import deepcopy
from threading import Lock
from time import perf_counter
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import get_db

from app.database.models.candidate import Candidate
from app.database.models.resume import Resume
from app.storage.s3_resume import generate_resume_presigned_url

from app.search.schema import SearchRequirement
from app.search.service import build_routing_packet
from app.search.spelling import build_speller, suggest_query_correction

from app.intelligence.pipeline import execute_search
from app.intelligence.seniority_policy import get_seniority_policy


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("app.search.api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    build_speller()
    yield


def _seniority_filter_for_response(specification, structured: dict) -> dict | None:
    requirement = next(
        (
            item
            for item in specification.requirements
            if (item.field or "").casefold() == "seniority"
            and item.mandatory
            and not item.negated
            and set(item.capabilities)
            & {"structured_candidate_lookup", "structured_experience_lookup"}
        ),
        None,
    )
    if requirement is None or not isinstance(requirement.value, str):
        return None

    policy = get_seniority_policy(requirement.value)
    roles = list(structured.get("roles") or [])
    experience_scope = policy.experience_scope
    if experience_scope == "RELEVANT_ROLE" and not roles:
        experience_scope = "OVERALL"

    return {
        "seniority": policy.seniority,
        "preferred_min_months": policy.preferred_min_months,
        "preferred_max_months": policy.preferred_max_months,
        "acceptable_min_months": policy.acceptable_min_months,
        "acceptable_max_months": policy.acceptable_max_months,
        "experience_scope": experience_scope,
        "role_titles": roles,
    }


# ============================================================
# FastAPI application
# ============================================================

app = FastAPI(
    title="GenieHire Recruiter Search API",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Request schemas
# ============================================================

class SearchRequest(BaseModel):
    query: str

    # Kept for backwards compatibility with older frontend builds.
    # New filter-panel flow should use /search/refine instead.
    skills: list[str] = Field(default_factory=list)

    debug: bool = False


class LocationFilter(BaseModel):
    """A selected Geoapify place normalized into geographic components."""
    place_id: str
    label: str
    city: str | None = None
    state: str | None = None
    country: str | None = None


class RuntimeFilters(BaseModel):
    skills: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    locations: list[LocationFilter] = Field(default_factory=list)
    experience_min: float | None = Field(default=None, ge=0)
    experience_max: float | None = Field(default=None, ge=0)
    companies: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


class RefineSearchRequest(BaseModel):
    search_id: str
    filters: RuntimeFilters = Field(default_factory=RuntimeFilters)
    debug: bool = False


_ROUTING_PACKET_STORE: dict[str, object] = {}
_ROUTING_PACKET_LOCK = Lock()


# ============================================================
# Runtime filter helpers
# ============================================================


def _clean_filter_values(values: list[str]) -> list[str]:
    """Remove empty and case-insensitive duplicate filter values."""
    cleaned: list[str] = []

    for value in values:
        item = str(value).strip()
        if not item:
            continue

        if not any(existing.casefold() == item.casefold() for existing in cleaned):
            cleaned.append(item)

    return cleaned


def _remove_runtime_requirements(routing_packet) -> None:
    """Remove requirements previously created by the runtime filter layer."""
    specification = routing_packet.specification
    specification.requirements = [
        requirement
        for requirement in specification.requirements
        if not requirement.id.startswith("runtime_filter_")
    ]


def _make_runtime_requirement(
    *,
    requirement_id: str,
    text: str,
    field: str,
    relationship: str = "AND",
    group_id: str | None = None,
    location_scope: str | None = None,
) -> SearchRequirement:
    """Build a structured requirement generated by a UI filter."""
    normalized = text.strip().casefold()

    return SearchRequirement(
        id=requirement_id,
        original_text=text.strip(),
        normalized_text=normalized,
        type="STRUCTURED",
        mandatory=True,
        match_mode="HARD",
        source_of_truth=(
            "candidate_skills"
            if field == "skills"
            else "candidate_experience"
            if field in {"roles", "companies"}
            else "candidate_location"
            if field == "location"
            else "candidate_total_experience"
        ),
        capabilities=["structured_candidate_lookup"],
        relationship=relationship,
        group_id=group_id,
        field=field,
        value=text.strip(),
        equivalent_terms=[text.strip()],
        location_scope=location_scope,
        confidence=1.0,
    )


SENIORITY_BANDS: dict[str, tuple[float, float | None]] = {
    "entry": (0.0, 2.0),
    "mid": (3.0, 7.0),
    "senior": (8.0, None),
}


def _seniority_ranges(selected: list[str]) -> list[tuple[float, float | None]]:
    """Translate UI seniority labels into total-experience ranges."""
    ranges: list[tuple[float, float | None]] = []
    for value in selected:
        bounds = SENIORITY_BANDS.get(value.strip().casefold())
        if bounds is not None:
            ranges.append(bounds)

    return ranges


def _intersect_experience_ranges(
    left: tuple[float, float | None],
    right: tuple[float, float | None],
) -> tuple[float, float | None] | None:
    """Intersect ranges whose maximum includes the named full year."""
    minimum = max(left[0], right[0])
    finite_maxima = [maximum for maximum in (left[1], right[1]) if maximum is not None]
    maximum = min(finite_maxima) if finite_maxima else None
    if maximum is not None and minimum >= maximum + 1:
        return None
    return minimum, maximum


def _make_runtime_experience_requirement(
    minimum: float | None,
    maximum: float | None,
    *,
    index: int,
    relationship: str = "AND",
    group_id: str | None = None,
    original_text: str | None = None,
) -> SearchRequirement:
    label = original_text or (
        f"{minimum:g}+ years experience"
        if maximum is None
        else f"{minimum:g}-{maximum:g} years experience"
        if minimum is not None
        else f"up to {maximum:g} years experience"
    )
    return SearchRequirement(
        id=f"runtime_filter_experience_{index}",
        original_text=label,
        normalized_text=label.casefold(),
        type="STRUCTURED",
        mandatory=True,
        match_mode="HARD",
        source_of_truth="candidate_total_experience",
        capabilities=["structured_candidate_lookup"],
        relationship=relationship,
        group_id=group_id,
        field="experience",
        value={
            "min_experience_years": minimum,
            "max_experience_years": maximum,
        },
        confidence=1.0,
    )


def _apply_runtime_filters(base_routing_packet, filters: RuntimeFilters):

    routing_packet = deepcopy(base_routing_packet)
    specification = routing_packet.specification

    _remove_runtime_requirements(routing_packet)

    skills = _clean_filter_values(filters.skills)
    roles = _clean_filter_values(filters.roles)
    seniority = _clean_filter_values(filters.seniority)
    companies = _clean_filter_values(filters.companies)
    domains = _clean_filter_values([domain.upper() for domain in filters.domains])
    # Accept only selected Geoapify suggestions, never arbitrary typed text.
    locations = []
    seen_locations = set()
    for location in filters.locations:
        payload = location.model_dump()
        city = (payload.get("city") or "").strip() or None
        state = (payload.get("state") or "").strip() or None
        country = (payload.get("country") or "").strip() or None
        label = (payload.get("label") or "").strip()
        place_id = (payload.get("place_id") or "").strip()
        if not any((city, state, country)) or not label or not place_id:
            continue
        payload.update(city=city, state=state, country=country, label=label, place_id=place_id)
        key = tuple((payload.get(part) or "").casefold() for part in ("city", "state", "country"))
        if key not in seen_locations:
            seen_locations.add(key)
            locations.append(payload)

    # --------------------------------------------------------
    # Skills: AND semantics
    # --------------------------------------------------------
    for index, skill in enumerate(skills, start=1):
        specification.requirements.append(
            _make_runtime_requirement(
                requirement_id=f"runtime_filter_skill_{index}",
                text=skill,
                field="skills",
            )
        )

    base_skills = list(specification.skills or [])
    specification.skills = _clean_filter_values(base_skills + skills)

    # --------------------------------------------------------
    # Roles: OR semantics within the filter, AND with the base query
    # --------------------------------------------------------
    if roles:
        role_group_id = "runtime_filter_roles"

        for index, role in enumerate(roles, start=1):
            specification.requirements.append(
                _make_runtime_requirement(
                    requirement_id=f"runtime_filter_role_{index}",
                    text=role,
                    field="roles",
                    relationship="OR" if len(roles) > 1 else "AND",
                    group_id=role_group_id if len(roles) > 1 else None,
                )
            )

        specification.roles = _clean_filter_values(
            list(specification.roles or []) + roles
        )

    # --------------------------------------------------------
    # Companies: OR semantics within the filter
    # --------------------------------------------------------
    if companies:
        company_group_id = "runtime_filter_companies"
        for index, company in enumerate(companies, start=1):
            specification.requirements.append(
                _make_runtime_requirement(
                    requirement_id=f"runtime_filter_company_{index}",
                    text=company,
                    field="companies",
                    relationship="OR" if len(companies) > 1 else "AND",
                    group_id=company_group_id if len(companies) > 1 else None,
                )
            )
        specification.companies = _clean_filter_values(
            list(specification.companies or []) + companies
        )

    if domains:
        domain_label = ", ".join(domains)
        specification.requirements.append(
            SearchRequirement(
                id="runtime_filter_domains",
                original_text=f"Candidate domain: {domain_label}",
                normalized_text=f"candidate domain: {domain_label}".casefold(),
                type="STRUCTURED",
                mandatory=True,
                match_mode="HARD",
                source_of_truth="candidate_resume",
                capabilities=["structured_candidate_lookup"],
                field="domains",
                value=domains,
                equivalent_terms=domains,
                confidence=1.0,
            )
        )

    # --------------------------------------------------------
    # Candidate locations: OR semantics within the filter
    # --------------------------------------------------------
    if locations:
        location_group_id = "runtime_filter_locations"

        for index, location in enumerate(locations, start=1):
            # Convert the structured location into a string because
            # _make_runtime_requirement() expects text, not a dictionary.
            location_text = ", ".join(
                part
                for part in (
                    location.get("city"),
                    location.get("state"),
                    location.get("country"),
                )
                if part
            )

            specification.requirements.append(
                _make_runtime_requirement(
                    requirement_id=f"runtime_filter_location_{index}",
                    text=location_text,
                    field="location",
                    relationship="OR" if len(locations) > 1 else "AND",
                    group_id=location_group_id if len(locations) > 1 else None,
                    location_scope="CANDIDATE",
                )
            )

    # --------------------------------------------------------
    # Seniority: OR semantics between selected bands
    # --------------------------------------------------------
    seniority_ranges = _seniority_ranges(seniority)
    experience_range = (
        filters.experience_min,
        filters.experience_max,
    )
    has_experience_filter = any(value is not None for value in experience_range)

    if seniority_ranges and has_experience_filter:
        filtered_ranges = []
        for value in seniority:
            band_key = value.strip().casefold()
            band_range = SENIORITY_BANDS.get(band_key)
            if band_range is None:
                continue
            intersection = _intersect_experience_ranges(
                band_range,
                (
                    experience_range[0] if experience_range[0] is not None else 0.0,
                    experience_range[1],
                ),
            )
            if intersection is not None:
                filtered_ranges.append((intersection, value))
        ranges = [intersection for intersection, _ in filtered_ranges]
        if not ranges:
            raise ValueError("Experience range and seniority selection don't overlap.")
    elif seniority_ranges:
        ranges = seniority_ranges
        filtered_ranges = [(item, None) for item in ranges]
    elif has_experience_filter:
        ranges = [experience_range]
        filtered_ranges = [(ranges[0], None)]
    else:
        ranges = []
        filtered_ranges = []

    runtime_minimum: float | None = None
    if ranges:
        grouped_seniority = len(seniority_ranges) > 1
        group_id = "runtime_filter_seniority" if grouped_seniority else None
        for index, ((minimum, maximum), band_text) in enumerate(
            filtered_ranges,
            start=1,
        ):
            specification.requirements.append(
                _make_runtime_experience_requirement(
                    minimum,
                    maximum,
                    index=index,
                    relationship="OR" if grouped_seniority else "AND",
                    group_id=group_id,
                    original_text=band_text,
                )
            )


        runtime_minimums = [
            minimum for minimum, _ in ranges if minimum is not None
        ]
        runtime_minimum = min(runtime_minimums) if runtime_minimums else None
        runtime_maximums = [maximum for _, maximum in ranges]
        runtime_maximum = (
            max(runtime_maximums)
            if all(maximum is not None for maximum in runtime_maximums)
            else None
        )
        base_minimum = specification.min_experience_years
        base_maximum = specification.max_experience_years
        minimums = [
            value for value in (base_minimum, runtime_minimum) if value is not None
        ]
        specification.min_experience_years = max(minimums) if minimums else None
        finite_maximums = [
            value for value in (base_maximum, runtime_maximum) if value is not None
        ]
        specification.max_experience_years = (
            min(finite_maximums) if finite_maximums else None
        )


    structured = dict(routing_packet.structured_requirements or {})
    structured["skills"] = list(specification.skills or [])
    structured["roles"] = list(specification.roles or [])
    structured["companies"] = list(specification.companies or [])
    structured["domains"] = domains
    if locations:
        # The legacy summary has a scalar location field. The full selected
        # location set is preserved in the requirement graph (OR semantics).
        structured["location_filters"] = locations
        structured["location_scope"] = "CANDIDATE"
    structured["min_experience_years"] = specification.min_experience_years
    structured["max_experience_years"] = specification.max_experience_years
    if (
        runtime_minimum is not None
        and (base_minimum is None or runtime_minimum > base_minimum)
    ):
        structured["min_experience_exclusive"] = False

    if specification.roles:
        structured["role"] = specification.roles[0]

    routing_packet.structured_requirements = structured

    return routing_packet


def _store_routing_packet(search_id: str, routing_packet) -> None:
    with _ROUTING_PACKET_LOCK:
        _ROUTING_PACKET_STORE[search_id] = deepcopy(routing_packet)


def _get_routing_packet(search_id: str):
    with _ROUTING_PACKET_LOCK:
        routing_packet = _ROUTING_PACKET_STORE.get(search_id)
        return deepcopy(routing_packet) if routing_packet is not None else None


# ============================================================
# Health check
# ============================================================

@app.get("/")
def root():
    return {
        "service": "GenieHire Recruiter Search API",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
    }


# ============================================================
# Search endpoint
# ============================================================

@app.post("/search/suggestion")
def suggest_search_query(request: SearchRequest):
    """Check a query for a conservative spelling correction before search."""

    query = request.query.strip()

    if not query:
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty.",
        )

    return {
        "suggested_query": suggest_query_correction(query),
    }


@app.post("/search")
def search_candidates(
    request: SearchRequest,
    db: Session = Depends(get_db),
):

    query = request.query.strip()

    if not query:
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty.",
        )

    # Clean manually supplied skills.
    # Remove empty values and duplicate skills while preserving order.
    manual_skills = []

    for skill in request.skills:
        cleaned_skill = skill.strip()

        if not cleaned_skill:
            continue

        if not any(
            existing.lower() == cleaned_skill.lower()
            for existing in manual_skills
        ):
            manual_skills.append(cleaned_skill)

    search_id = str(uuid.uuid4())
    request_started = perf_counter()

    logger.info(
        "SEARCH REQUEST search_id=%s query_chars=%d manual_skills=%s",
        search_id,
        len(query),
        manual_skills,
    )

    try:

        # ----------------------------------------------------
        # 1. Search Layer
        # ----------------------------------------------------

        parsing_started = perf_counter()

        logger.info(
            "SEARCH STAGE search_id=%s stage=query_parsing status=started",
            search_id,
        )

        routing_packet = build_routing_packet(
            query,
            manual_skills=manual_skills,
        )

        _store_routing_packet(search_id, routing_packet)

        specification = routing_packet.specification

        logger.info(
            "SEARCH STAGE search_id=%s "
            "stage=query_parsing status=complete "
            "duration_s=%.3f route=%s requirements=%d assumptions=%d",
            search_id,
            perf_counter() - parsing_started,
            routing_packet.route,
            len(specification.requirements),
            len(specification.assumptions),
        )

        # ----------------------------------------------------
        # 2. Intelligence Layer
        # ----------------------------------------------------

        execution_trace = {
            "search_id": search_id,
            "debug": request.debug,
            "manual_skills": manual_skills,
        }

        results = execute_search(
            db=db,
            query=query,
            routing_packet=routing_packet,
            trace=execution_trace,
        )

        specification = routing_packet.specification

        structured = (
            routing_packet.structured_requirements
        )

        semantic_requirements = (
            routing_packet.semantic_requirements
        )

        relevant_experience_months = [
            requirement.minimum_relevant_experience_months
            for requirement in specification.requirements
            if requirement.minimum_relevant_experience_months is not None
        ]

        temporal_windows = [
            requirement.temporal_window_months
            for requirement in specification.requirements
            if requirement.type.upper() == "TEMPORAL"
            and requirement.temporal_window_months is not None
        ]

        parsed_response = {
            "original_query": query,

            "requested_count": (
                specification.requested_count
            ),

            "count_explicit": specification.count_explicit,

            "structured_requirements": {
                "skills": (
                    structured.get("skills")
                    or []
                ),

                "roles": structured.get("roles") or [],

                "companies": structured.get("companies") or [],
                "domains": structured.get("domains") or [],

                "location": structured.get("location"),

                "role": (
                    (
                        structured.get("roles")
                        or [None]
                    )[0]
                ),

                "recency_months": (
                    temporal_windows[0]
                    if len(temporal_windows) == 1
                    else None
                ),

                "experience_min_years": (
                    structured.get(
                        "min_experience_years"
                    )
                ),

                "experience_max_years": (
                    structured.get(
                        "max_experience_years"
                    )
                ),

                "relevant_experience_min_years": (
                    max(relevant_experience_months) / 12
                    if relevant_experience_months
                    else None
                ),

                "experience_scope": (
                    "RELEVANT"
                    if relevant_experience_months
                    else "OVERALL"
                ),
                "seniority_filter": _seniority_filter_for_response(
                    specification,
                    structured,
                ),
            },

            "semantic_requirement": (
                semantic_requirements[0]
                if semantic_requirements
                else None
            ),

            "semantic_requirements": semantic_requirements,

            "assumptions": specification.assumptions,

            "requirements": [
                item.model_dump(exclude_none=True)
                for item in specification.requirements
            ],

            "exclusions": [
                item.original_text
                for item in specification.requirements
                if item.negated
            ],
        }

        # ----------------------------------------------------
        # 4. Response
        # ----------------------------------------------------

        response = {
            "route": routing_packet.route,

            "suggested_query": suggest_query_correction(
                query
            ),

            "search_specification": specification.model_dump(
                exclude_none=True
            ),

            "search_id": search_id,

            "execution_plan": execution_trace.get(
                "execution_plan",
                {},
            ),

            "execution_trace": execution_trace,

            "parsed": parsed_response,

            "results": results,

            "message": (
                f"Found {len(results)} matching "
                f"candidate"
                f"{'' if len(results) == 1 else 's'}."
            ),

            "valid": True,

            "errors": [],
        }

        logger.info(
            "SEARCH COMPLETE search_id=%s route=%s results=%d total_s=%.3f",
            search_id,
            routing_packet.route,
            len(results),
            perf_counter() - request_started,
        )

        return response

    except ValueError as exc:

        logger.warning(
            "SEARCH INVALID search_id=%s duration_s=%.3f error=%s",
            search_id,
            perf_counter() - request_started,
            exc,
        )

        return {
            "route": "STRUCTURED",

            "parsed": {
                "original_query": query,

                "requested_count": 10,

                "count_explicit": False,

                "structured_requirements": {
                    "skills": [],
                    "location": None,
                    "role": None,
                    "recency_months": None,
                    "experience_min_years": None,
                    "experience_scope": None,
                },

                "semantic_requirement": None,

                "exclusions": [],
            },

            "results": [],

            "message": None,

            "valid": False,

            "errors": [
                str(exc)
            ],
        }

    except Exception as exc:

        logger.exception(
            "SEARCH FAILED search_id=%s duration_s=%.3f error=%s",
            search_id,
            perf_counter() - request_started,
            exc,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "An error occurred while "
                "processing the search."
            ),
        )

@app.post("/search/refine")
def refine_search(
    request: RefineSearchRequest,
    db: Session = Depends(get_db),
):

    request_started = perf_counter()
    search_id = request.search_id.strip()

    if not search_id:
        raise HTTPException(
            status_code=400,
            detail="search_id is required.",
        )

    base_routing_packet = _get_routing_packet(search_id)

    if base_routing_packet is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Search session not found or expired. "
                "Run the original search again."
            ),
        )

    filters = request.filters

    logger.info(
        "REFINE REQUEST search_id=%s skills=%s roles=%s seniority=%s "
        "experience_min=%s experience_max=%s companies=%s locations=%s",
        search_id,
        filters.skills,
        filters.roles,
        filters.seniority,
        filters.experience_min,
        filters.experience_max,
        filters.companies,
        filters.locations,
    )

    try:
        refined_routing_packet = _apply_runtime_filters(
            base_routing_packet,
            filters,
        )

        execution_trace = {
            "search_id": search_id,
            "debug": request.debug,
            "refinement": True,
            "manual_skills": _clean_filter_values(filters.skills),
            "runtime_filters": filters.model_dump(exclude_none=True),
        }

        logger.info(
            "SEARCH STAGE search_id=%s stage=runtime_filter_application "
            "status=complete route=%s requirements=%d",
            search_id,
            refined_routing_packet.route,
            len(refined_routing_packet.specification.requirements),
        )

        results = execute_search(
            db=db,
            query=refined_routing_packet.query,
            routing_packet=refined_routing_packet,
            trace=execution_trace,
        )

        specification = refined_routing_packet.specification
        structured = refined_routing_packet.structured_requirements or {}
        semantic_requirements = refined_routing_packet.semantic_requirements or []

        relevant_experience_months = [
            requirement.minimum_relevant_experience_months
            for requirement in specification.requirements
            if requirement.minimum_relevant_experience_months is not None
        ]

        temporal_windows = [
            requirement.temporal_window_months
            for requirement in specification.requirements
            if requirement.type.upper() == "TEMPORAL"
            and requirement.temporal_window_months is not None
        ]

        parsed_response = {
            "original_query": refined_routing_packet.query,
            "requested_count": specification.requested_count,
            "count_explicit": specification.count_explicit,
            "structured_requirements": {
                "skills": structured.get("skills") or [],
                "roles": structured.get("roles") or [],
                "companies": structured.get("companies") or [],
                "domains": structured.get("domains") or [],
                "location": structured.get("location"),
                "role": (structured.get("roles") or [None])[0],
                "recency_months": (
                    temporal_windows[0]
                    if len(temporal_windows) == 1
                    else None
                ),
                "experience_min_years": structured.get(
                    "min_experience_years"
                ),
                "experience_max_years": structured.get(
                    "max_experience_years"
                ),
                "relevant_experience_min_years": (
                    max(relevant_experience_months) / 12
                    if relevant_experience_months
                    else None
                ),
                "experience_scope": (
                    "RELEVANT"
                    if relevant_experience_months
                    else "OVERALL"
                ),
                "seniority_filter": _seniority_filter_for_response(
                    specification,
                    structured,
                ),
            },
            "semantic_requirement": (
                semantic_requirements[0]
                if semantic_requirements
                else None
            ),
            "semantic_requirements": semantic_requirements,
            "assumptions": specification.assumptions,
            "requirements": [
                item.model_dump(exclude_none=True)
                for item in specification.requirements
            ],
            "exclusions": [
                item.original_text
                for item in specification.requirements
                if item.negated
            ],
            "runtime_filters": filters.model_dump(exclude_none=True),
        }

        response = {
            "route": refined_routing_packet.route,
            "search_id": search_id,
            "suggested_query": None,
            "search_specification": specification.model_dump(
                exclude_none=True
            ),
            "execution_plan": execution_trace.get(
                "execution_plan", {}
            ),
            "execution_trace": execution_trace,
            "parsed": parsed_response,
            "results": results,
            "message": (
                f"Found {len(results)} matching candidate"
                f"{'' if len(results) == 1 else 's'}."
            ),
            "valid": True,
            "errors": [],
        }

        logger.info(
            "REFINE COMPLETE search_id=%s results=%d total_s=%.3f",
            search_id,
            len(results),
            perf_counter() - request_started,
        )

        return response

    except ValueError as exc:
        logger.warning(
            "REFINE INVALID search_id=%s duration_s=%.3f error=%s",
            search_id,
            perf_counter() - request_started,
            exc,
        )

        return {
            "route": base_routing_packet.route,
            "search_id": search_id,
            "parsed": {
                "original_query": base_routing_packet.query,
                "requested_count": base_routing_packet.specification.requested_count,
                "count_explicit": base_routing_packet.specification.count_explicit,
                "structured_requirements": {
                    "skills": [],
                    "roles": [],
                    "location": None,
                    "role": None,
                    "recency_months": None,
                    "experience_min_years": None,
                    "experience_max_years": None,
                    "experience_scope": None,
                },
                "semantic_requirement": None,
                "exclusions": [],
            },
            "results": [],
            "message": None,
            "valid": False,
            "errors": [str(exc)],
        }

    except Exception as exc:
        logger.exception(
            "REFINE FAILED search_id=%s duration_s=%.3f error=%s",
            search_id,
            perf_counter() - request_started,
            exc,
        )

        raise HTTPException(
            status_code=500,
            detail="An error occurred while refining the search.",
        )


# ============================================================
# View resume endpoint
# ============================================================

@app.get(
    "/candidates/{candidate_id}/resume"
)
def view_candidate_resume(
    candidate_id: int,
    db: Session = Depends(get_db),
):
    """
    Return the resume URL for a candidate.

    Frontend expects:

        {
            "candidate_id": 123,
            "resume_url": "..."
        }
    """

    resume_started = perf_counter()

    logger.info(
        "RESUME REQUEST candidate_id=%d",
        candidate_id,
    )

    # --------------------------------------------------------
    # Find candidate
    # --------------------------------------------------------

    candidate = db.scalar(
        select(Candidate).where(
            Candidate.id == candidate_id
        )
    )

    if candidate is None:

        logger.warning(
            "RESUME NOT_FOUND candidate_id=%d reason=candidate",
            candidate_id,
        )

        raise HTTPException(
            status_code=404,
            detail="Candidate not found.",
        )

    # --------------------------------------------------------
    # Find resume
    # --------------------------------------------------------

    resume = db.scalar(
        select(Resume)
        .where(
            Resume.candidate_id
            == candidate_id
        )
        .order_by(
            Resume.id.desc()
        )
    )

    if resume is None:

        logger.warning(
            "RESUME NOT_FOUND candidate_id=%d reason=resume",
            candidate_id,
        )

        raise HTTPException(
            status_code=404,
            detail=(
                "Resume not found for "
                "this candidate."
            ),
        )

    # --------------------------------------------------------
    # Resolve storage URL
    # --------------------------------------------------------

    storage_key = getattr(
        resume,
        "storage_key",
        None,
    )

    if not storage_key:

        logger.warning(
            "RESUME NOT_FOUND candidate_id=%d reason=storage_key",
            candidate_id,
        )

        raise HTTPException(
            status_code=404,
            detail=(
                "Resume storage URL is not "
                "available."
            ),
        )

    resume_url = generate_resume_presigned_url(
        storage_key
    )

    logger.info(
        "RESUME READY candidate_id=%d duration_s=%.3f",
        candidate_id,
        perf_counter() - resume_started,
    )

    # --------------------------------------------------------
    # Return frontend-compatible response
    # --------------------------------------------------------

    return {
        "candidate_id": candidate_id,
        "resume_url": resume_url,
    }
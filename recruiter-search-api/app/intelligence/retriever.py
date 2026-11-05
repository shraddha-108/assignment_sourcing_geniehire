
import os
import re
import math
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.candidate import Candidate
from app.database.models.candidate_skill import CandidateSkill
from app.database.models.company import Company
from app.database.models.experience import Experience
from app.database.models.experience_skill import ExperienceSkill
from app.database.models.role import Role
from app.database.models.resume import Resume
from app.database.models.skill import Skill
from app.database.location_utils import location_matches

from app.ingestion.vector.retrieval import retrieve_semantic_candidates
from app.search.normalization import (
    canonicalize_semantic_requirement,
    company_name_matches,
    equivalent_terms,
    expand_semantic_requirement,
    role_matches as _role_matches,
)


STRUCTURED_RETRIEVAL_LIMIT = int(
    os.getenv(
        "STRUCTURED_RETRIEVAL_LIMIT",
        "500",
    )
)

SEMANTIC_RETRIEVAL_LIMIT = int(
    os.getenv(
        "SEMANTIC_RETRIEVAL_LIMIT",
        "200",
    )
)


def _normalize(value: str | None) -> str:
    if not value:
        return ""

    return " ".join(
        value.lower().strip().split()
    )


def _as_date(value) -> date | None:
    """Normalize SQL date/datetime/ISO values to date."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _months_between(start: date, end: date) -> int:
    """Return completed calendar months between two dates."""
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    return max(0, months)


def _combined_experience_months(
    experiences: list[Experience],
) -> int:
    """
    Sum experience durations without double-counting overlapping jobs.
    Experiences without a valid start date do not contribute.
    """
    today = date.today()
    intervals: list[tuple[date, date]] = []

    for experience in experiences:
        start = _as_date(experience.start_date)
        if start is None:
            continue

        end = (
            today
            if getattr(experience, "is_current", False)
            else _as_date(experience.end_date)
        )
        if end is None or end < start:
            continue

        intervals.append((start, end))

    if not intervals:
        return 0

    intervals.sort(key=lambda interval: interval[0])
    merged: list[list[date]] = []

    for start, end in intervals:
        if not merged or start > merged[-1][1] + timedelta(days=1):
            merged.append([start, end])
        elif end > merged[-1][1]:
            merged[-1][1] = end

    return sum(_months_between(start, end) for start, end in merged)


def _candidate_seniority_experience_months(
    db: Session,
    candidate: Candidate,
    seniority_filter: dict,
) -> int:
    """
    Resolve experience months for a seniority policy.

    OVERALL uses the candidate's precomputed total. RELEVANT_ROLE sums
    only experience records whose titles match the requested role family.
    """
    scope = seniority_filter.get("experience_scope", "OVERALL")

    if scope != "RELEVANT_ROLE":
        return int(candidate.total_experience_months or 0)

    requested_roles = seniority_filter.get("role_titles") or []
    if not requested_roles:
        return int(candidate.total_experience_months or 0)

    experiences = db.scalars(
        select(Experience)
        .join(Role, Role.id == Experience.role_id)
        .where(Experience.candidate_id == candidate.id)
    ).all()

    matching_experiences = [
        experience
        for experience in experiences
        if experience.role
        and experience.role.title
        and any(
            _role_matches(requested_role, experience.role.title)
            for requested_role in requested_roles
        )
    ]

    return _combined_experience_months(matching_experiences)


def retrieve_structured_candidates(
    db: Session,
    requirements: dict,
) -> list[dict]:
    """
    Retrieve candidates using PostgreSQL only.

    This function performs discovery using exact/
    structured candidate facts.

    It does NOT perform semantic retrieval.

    Location semantics:
    - CANDIDATE: match Candidate.location.
    - EXPERIENCE: requires an experience-level location field
      in the Experience model. This retriever intentionally does
      not fall back to Candidate.location because that would
      incorrectly turn an employment-location requirement into
      a candidate-location requirement.
    """

    skills = requirements.get(
    "skills"
    ) or []

    negated_skills = requirements.get(
        "negated_skills"
    ) or []

    roles = requirements.get(
        "roles"
    ) or []

    negated_roles = requirements.get(
        "negated_roles"
    ) or []

    companies = requirements.get(
        "companies"
    ) or []

    domains = {
        str(domain).strip().upper()
        for domain in requirements.get("domains") or []
        if str(domain).strip()
    }

    negated_companies = requirements.get(
        "negated_companies"
    ) or []

    location = _normalize(
        requirements.get("location")
    )


    location_filters = requirements.get("location_filters") or []

    location_scope = (
        requirements.get("location_scope")
        or "CANDIDATE"
    )

    location_negated = requirements.get(
        "location_negated",
        False,
    )

    min_experience = requirements.get(
    "min_experience_years"
    )

    max_experience = requirements.get(
        "max_experience_years"
    )

    experience_negated = requirements.get(
        "experience_negated",
        False,
    )

    seniority_filter = requirements.get("seniority_filter")

    query = select(
        Candidate
    ).distinct()

    if domains:
        domain_exists = (
            select(Resume.candidate_id)
            .where(
                Resume.candidate_id == Candidate.id,
                func.upper(Resume.primary_domain).in_(domains),
            )
            .exists()
        )
        query = query.where(domain_exists)



    skill_aliases = requirements.get("skill_aliases") or {}

    def _skill_names(requested_skill: str) -> set[str]:
        names = {_normalize(requested_skill)}

        aliases = skill_aliases.get(requested_skill)
        if aliases is None:
            aliases = skill_aliases.get(
                _normalize(requested_skill),
                [],
            )

        if isinstance(aliases, str):
            aliases = [aliases]

        names.update(
            _normalize(alias)
            for alias in aliases
            if alias
        )
        return {name for name in names if name}

    if skills:
        for requested_skill in skills:
            normalized_skill_names = _skill_names(
                requested_skill
            )

            if not normalized_skill_names:
                continue

            if roles:
                skill_exists = (
                    select(ExperienceSkill.candidate_id)
                    .join(Skill, Skill.id == ExperienceSkill.skill_id)
                    .where(
                        ExperienceSkill.candidate_id == Candidate.id,
                        Skill.normalized_name.in_(normalized_skill_names),
                    )
                    .exists()
                )
            else:
                skill_exists = (
                    select(CandidateSkill.candidate_id)
                    .join(
                        Skill,
                        Skill.id == CandidateSkill.skill_id,
                    )
                    .where(
                        CandidateSkill.candidate_id == Candidate.id,
                        Skill.normalized_name.in_(
                            normalized_skill_names
                        ),
                    )
                    .exists()
                )

            query = query.where(skill_exists)



    if roles or negated_roles:
        candidates = db.scalars(
            query
        ).all()

        filtered = []

        for candidate in candidates:
            experiences = db.scalars(
                select(Experience)
                .join(
                    Role,
                    Role.id == Experience.role_id,
                )
                .where(
                    Experience.candidate_id == candidate.id
                )
            ).all()

            role_titles = [
                experience.role.title
                for experience in experiences
                if experience.role and experience.role.title
            ]

            if roles:
                positive_match = all(
                    any(
                        _role_matches(
                            requested_role,
                            role_title,
                        )
                        for role_title in role_titles
                    )
                    for requested_role in roles
                )

                if not positive_match:
                    continue

            if negated_roles:
                excluded = any(
                    _role_matches(
                        excluded_role,
                        role_title,
                    )
                    for excluded_role in negated_roles
                    for role_title in role_titles
                )

                if excluded:
                    continue

            filtered.append(candidate)

        candidates = filtered

    else:
        candidates = db.scalars(
            query
        ).all()

    # --------------------------------------------------
    # Location filter

    if location and not location_filters:

        if location_scope == "CANDIDATE":

            candidates = [
                candidate
                for candidate in candidates
                if (
                    not location_matches(
                        location,
                        candidate.location,
                    )
                    if location_negated
                    else location_matches(
                        location,
                        candidate.location,
                    )
                )
            ]

        elif location_scope == "EXPERIENCE":

            candidates = []

        else:

            # Unknown/invalid scope should never silently become candidate location.
            candidates = []

    # Runtime Geoapify selections are candidate-location filters. Multiple
    # selections are OR'd with each other and AND'd with the base query.
    if location_filters:
        def _normalized_location_part(value):
            return " ".join((value or "").casefold().strip().split())

        def _matches_selected_location(candidate, selected):
            candidate_location = candidate.location
            if candidate_location is None:
                return False
            selected_city = _normalized_location_part(selected.get("city"))
            selected_state = _normalized_location_part(selected.get("state"))
            selected_country = _normalized_location_part(selected.get("country"))
            actual_city = _normalized_location_part(candidate_location.normalized_city or candidate_location.city)
            actual_state = _normalized_location_part(candidate_location.normalized_state or candidate_location.state)
            actual_country = _normalized_location_part(candidate_location.normalized_country or candidate_location.country)
            if not any((selected_city, selected_state, selected_country)):
                return False
            if selected_city and actual_city != selected_city:
                return False
            if selected_state and actual_state != selected_state:
                return False
            if selected_country and actual_country != selected_country:
                return False
            return True

        candidates = [
            candidate for candidate in candidates
            if any(_matches_selected_location(candidate, selected) for selected in location_filters)
        ]

    # --------------------------------------------------
    # Company filter
    # --------------------------------------------------

    if companies:

        company_aliases = requirements.get("company_aliases") or {}
        company_terms = [
            company_aliases.get(company) or [company]
            for company in companies
            if company
        ]

        filtered = []

        for candidate in candidates:

            experiences = db.scalars(
                select(Experience)
                .join(
                    Company,
                    Company.id
                    == Experience.company_id,
                )
                .where(
                    Experience.candidate_id
                    == candidate.id
                )
            ).all()

            matched = False

            for experience in experiences:

                company_name = (
                    experience.company.name
                    if experience.company
                    else None
                )

                if any(company_name_matches(company_name, aliases) for aliases in company_terms):
                    matched = True
                    break

            if matched:
                filtered.append(
                    candidate
                )

        candidates = filtered

    # --------------------------------------------------
    # Negated company filter
    # --------------------------------------------------

    if negated_companies:
        normalized_excluded_companies = {
            _normalize(company)
            for company in negated_companies
            if company
        }

        filtered = []

        for candidate in candidates:
            experiences = db.scalars(
                select(Experience)
                .join(
                    Company,
                    Company.id == Experience.company_id,
                )
                .where(
                    Experience.candidate_id == candidate.id
                )
            ).all()

            excluded = any(
                _normalize(
                    experience.company.name
                    if experience.company
                    else None
                ) in normalized_excluded_companies
                for experience in experiences
            )

            if not excluded:
                filtered.append(candidate)

        candidates = filtered

    # --------------------------------------------------
    # Total experience filter
    # --------------------------------------------------

    if (
        min_experience is not None
        or max_experience is not None
    ):

        filtered = []

        for candidate in candidates:

            total_months = int(
                candidate.total_experience_months
                or 0
            )

            total_years = (
                total_months / 12.0
            )

            in_experience_range = True

            if min_experience is not None:
                minimum = float(min_experience)

                if requirements.get("min_experience_exclusive"):
                    if total_years <= minimum:
                        in_experience_range = False
                elif total_years < minimum:
                    in_experience_range = False

            if max_experience is not None:
                maximum = float(max_experience)

                if total_years >= maximum + 1:
                    in_experience_range = False

            if experience_negated:
                if in_experience_range:
                    continue
            elif not in_experience_range:
                continue

            filtered.append(
                candidate
            )

        candidates = filtered

    # --------------------------------------------------
    # Seniority filter
    # --------------------------------------------------

    if seniority_filter:
        acceptable_min = int(
            seniority_filter.get("acceptable_min_months", 0)
        )
        acceptable_max = seniority_filter.get("acceptable_max_months")

        filtered = []

        for candidate in candidates:
            experience_months = _candidate_seniority_experience_months(
                db,
                candidate,
                seniority_filter,
            )

            if experience_months < acceptable_min:
                continue

            if (
                acceptable_max is not None
                and experience_months > int(acceptable_max)
            ):
                continue

            filtered.append(candidate)

        candidates = filtered

    # --------------------------------------------------
    # Convert to pipeline format
    # --------------------------------------------------

    results = []

    for candidate in candidates:

        results.append(
            {
                "candidate": candidate,
                "candidate_id": candidate.id,
                "source": "structured",
                "retrieval_score": 1.0,
            }
        )

    return results


def retrieve_semantic(
    query: str,
    semantic_requirements: list[str],
    candidate_ids: list[int] | None = None,
    limit: int = SEMANTIC_RETRIEVAL_LIMIT,
) -> list[dict]:
    """
    Retrieve semantic evidence from Qdrant.

    Qdrant is used only for discovery.
    Qualification happens later.
    """

    if not semantic_requirements:
        return []

    unique_requirements = list(
        dict.fromkeys(
            requirement.strip()
            for requirement in semantic_requirements
            if requirement
            and requirement.strip()
        )
    )

    requirements = [
        {
            "evidence_query": _expand_semantic_query(
                requirement
            ),
            "value": requirement,
            "target": "",
            "type": "OTHER",
        }
        for requirement in unique_requirements
    ]

    if not requirements:
        return []

    # Retrieve each clause independently. A single
    # "A and B" embedding can miss candidates whose
    # evidence for A and B lives in different resume
    # sections; qualification below still requires
    # every mandatory clause.
    per_requirement_limit = max(
        20,
        math.ceil(
            limit / len(requirements)
        ),
    )

    evidence_by_key: dict[
        tuple[str, str],
        dict,
    ] = {}

    for requirement in requirements:

        requirement_text = str(
            requirement["value"]
        )

        reranker_query = (
            canonicalize_semantic_requirement(
                requirement_text
            )
        )

        hits = retrieve_semantic_candidates(
            query=requirement["evidence_query"],
            limit=per_requirement_limit,
            candidate_ids=candidate_ids,
            requirements=[requirement],
        )

        for item in hits:

            evidence_id = (
                item.get("evidence_id")
                or item.get("source_id")
            )

            text_key = " ".join(
                str(
                    item.get("text")
                    or ""
                )
                .casefold()
                .split()
            )

            evidence_key = (
                str(evidence_id)
                if evidence_id is not None
                else (
                    f"{item.get('candidate_id')}:"
                    f"{text_key}"
                )
            )

            key = (
                evidence_key,
                _normalize(
                    requirement_text
                ),
            )

            existing = evidence_by_key.get(
                key
            )

            if existing is None:

                existing = {
                    **item,
                    "retrieval_requirements": [
                        requirement_text
                    ],
                    "reranker_query": (
                        reranker_query
                    ),
                }

                evidence_by_key[key] = (
                    existing
                )

            else:

                item_score = float(
                    item.get(
                        "retrieval_score"
                    )
                    or 0.0
                )

                existing[
                    "retrieval_score"
                ] = (
                    float(
                        existing.get(
                            "retrieval_score"
                        )
                        or 0.0
                    )
                    + item_score
                )

                for source in item.get(
                    "retrieval_sources",
                    [],
                ):

                    if source not in existing.setdefault(
                        "retrieval_sources",
                        [],
                    ):
                        existing[
                            "retrieval_sources"
                        ].append(source)

    merged_evidence = list(
        evidence_by_key.values()
    )

    return sorted(
        merged_evidence,
        key=lambda item: float(
            item.get(
                "retrieval_score"
            )
            or 0.0
        ),
        reverse=True,
    )[:limit]


def _expand_semantic_query(
    requirement: str,
) -> str:
    return expand_semantic_requirement(
        requirement
    )

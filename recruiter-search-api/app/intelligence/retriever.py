
import os
import re
import math
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.candidate import Candidate
from app.database.models.candidate_skill import CandidateSkill
from app.database.models.company import Company
from app.database.models.experience import Experience
from app.database.models.role import Role
from app.database.models.skill import Skill
from app.database.location_utils import location_matches

from app.ingestion.vector.retrieval import retrieve_semantic_candidates
from app.search.normalization import (
    canonicalize_semantic_requirement,
    equivalent_terms,
    expand_semantic_requirement,
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


def _tokenize(value: str | None) -> list[str]:
    """Return role-title tokens in their original order."""
    if not value:
        return []

    return re.findall(
        r"[a-z0-9+#.]+",
        value.lower(),
    )


_ROLE_MODIFIER_TOKENS = {
    "senior",
    "sr",
    "junior",
    "jr",
    "lead",
    "principal",
    "staff",
    "associate",
    "trainee",
    "i",
    "ii",
    "iii",
    "iv",
    "v",
    "1",
    "2",
    "3",
    "4",
    "5",
}

_ROLE_DOMAIN_EXCLUSIONS = {
    "test",
    "testing",
    "qa",
    "quality",
    "assurance",
    "automation",
}


def _contains_role_phrase(
    actual_tokens: list[str],
    alias_tokens: list[str],
) -> bool:
    if not actual_tokens or not alias_tokens:
        return False
    width = len(alias_tokens)
    return any(
        actual_tokens[index:index + width] == alias_tokens
        for index in range(len(actual_tokens) - width + 1)
    )


def _role_matches(
    requested_role: str,
    actual_role: str | None,
) -> bool:
    """Match real role titles without broad token-subset false positives."""
    requested_tokens = list(_tokenize(requested_role))
    actual_tokens = list(_tokenize(actual_role))

    if not requested_tokens or not actual_tokens:
        return False

    aliases = equivalent_terms(requested_role, "role") or [requested_role]

    for alias in aliases:
        alias_tokens = list(_tokenize(alias))
        if not alias_tokens:
            continue

        if not _contains_role_phrase(actual_tokens, alias_tokens):
            continue

        extra_tokens = set(actual_tokens) - set(alias_tokens)

        # Domain modifiers such as QA/Test/Automation change the role domain
        # and must not match a generic developer request.
        if extra_tokens & _ROLE_DOMAIN_EXCLUSIONS:
            continue

        # A generic "developer" request should include specializations such
        # as Software Developer, Python Developer, Backend Developer, and
        # Full Stack Developer. Keep QA/Test/Automation roles excluded above.
        if requested_tokens == ["developer"]:
            return True

        # Seniority/level modifiers are legitimate variants of the same role.
        if extra_tokens <= _ROLE_MODIFIER_TOKENS:
            return True

        # If there are other words, only accept the exact role title. This
        # prevents titles such as "Software Engineer Manager" from being
        # treated as the requested individual-contributor role.
        if _normalize(actual_role) == _normalize(alias):
            return True

    return False


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

    negated_companies = requirements.get(
        "negated_companies"
    ) or []

    location = _normalize(
        requirements.get("location")
    )

    # Geoapify selections are already structured city/state/country filters.
    # Keep them separate from the legacy free-text location requirement.
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

    query = select(
        Candidate
    ).distinct()

    # --------------------------------------------------
    # Skill filter
    #
    # Positive skills are AND across requested skills.
    # Aliases are OR within one requested skill.
    # Negated skills are excluded completely.
    # --------------------------------------------------

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

    # Negative technology requirements are intentionally NOT hard SQL filters.
    # The validator must distinguish between:
    #   1. technology absent -> MATCH
    #   2. technology listed only as a candidate skill -> PARTIAL_MATCH
    #   3. technology used in meaningful work evidence -> EXCLUDE
    # Strict negative role/company/location/experience filters remain enforced
    # below.

    # --------------------------------------------------
    # Role filter
    #
    # Positive roles are AND across requested roles.
    # Negated roles exclude candidates who have any of them.
    # --------------------------------------------------

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
    #
    # IMPORTANT:
    # Do not treat an EXPERIENCE location requirement
    # as a candidate location requirement.
    #
    # The current retriever only has confirmed support
    # for Candidate.location. Experience-location
    # retrieval should be implemented after confirming
    # the Experience model's actual location field.
    # --------------------------------------------------

    # Apply the legacy free-text location matcher only when there are no
    # structured Geoapify selections. Otherwise the comma-separated label
    # (for example, "Pune, Maharashtra, India") would be compared as one
    # string against individual city/state/country fields and reject matches.
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

            # Do NOT fall back to candidate.location.
            #
            # If we do that, a candidate living in Pune
            # could incorrectly match:
            #
            #   "worked at TCS in Pune"
            #
            # even when their TCS experience was actually
            # in another location or the experience location
            # is unknown.
            #
            # Experience-level location retrieval should be
            # added once the Experience model's actual
            # location field is confirmed.
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

        normalized_companies = {
            _normalize(company)
            for company in companies
            if company
        }

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

                if (
                    _normalize(company_name)
                    in normalized_companies
                ):
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

            # --------------------------------------------------
            # Experience range semantics
            # --------------------------------------------------
            #
            # Positive:
            #   2-5 years -> KEEP candidates inside 2-5
            #
            # Negated:
            #   NOT fresher -> EXCLUDE candidates inside 0-1
            # --------------------------------------------------

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

                if total_years > maximum:
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

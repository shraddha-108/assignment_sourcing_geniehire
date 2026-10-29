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
from app.search.normalization import equivalent_terms, expand_semantic_requirement


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


def _tokenize(value: str | None) -> set[str]:
    if not value:
        return set()

    return set(
        re.findall(
            r"[a-z0-9+#.]+",
            value.lower(),
        )
    )


def _role_matches(
    requested_role: str,
    actual_role: str | None,
) -> bool:

    requested_tokens = _tokenize(
        requested_role
    )

    actual_tokens = _tokenize(
        actual_role
    )

    if not requested_tokens or not actual_tokens:
        return False

    aliases = equivalent_terms(requested_role, "role")
    return any(
        _tokenize(alias).issubset(actual_tokens)
        for alias in aliases
    ) or requested_tokens.issubset(actual_tokens)


def retrieve_structured_candidates(
    db: Session,
    requirements: dict,
) -> list[dict]:
    """
    Retrieve candidates using PostgreSQL only.

    This function performs discovery using exact/
    structured candidate facts.

    It does NOT perform semantic retrieval.
    """

    skills = requirements.get(
        "skills"
    ) or []

    roles = requirements.get(
        "roles"
    ) or []

    companies = requirements.get(
        "companies"
    ) or []

    location = _normalize(requirements.get("location"))

    min_experience = requirements.get(
        "min_experience_years"
    )

    max_experience = requirements.get(
        "max_experience_years"
    )

    query = select(
        Candidate
    ).distinct()

    # --------------------------------------------------
    # Skill filter
    # --------------------------------------------------

    if skills:
        normalized_skills = {
            _normalize(skill)
            for skill in skills
            if skill
        }
        for aliases in (requirements.get("skill_aliases") or {}).values():
            normalized_skills.update(_normalize(alias) for alias in aliases if alias)

        query = (
            query
            .join(
                CandidateSkill,
                CandidateSkill.candidate_id
                == Candidate.id,
            )
            .join(
                Skill,
                Skill.id
                == CandidateSkill.skill_id,
            )
            .where(
                Skill.normalized_name.in_(
                    normalized_skills
                )
            )
        )

    # --------------------------------------------------
    # Role filter
    #
    # We don't use SQL substring matching here.
    # Exact role validation happens later.
    # --------------------------------------------------

    if roles:

        role_query = (
            select(
                Experience.candidate_id
            )
            .join(
                Role,
                Role.id
                == Experience.role_id,
            )
            .where(
                Experience.candidate_id
                == Candidate.id
            )
        )

        candidates = db.scalars(
            query
        ).all()

        filtered = []

        for candidate in candidates:

            experiences = db.scalars(
                select(Experience)
                .join(
                    Role,
                    Role.id
                    == Experience.role_id,
                )
                .where(
                    Experience.candidate_id
                    == candidate.id
                )
            ).all()

            matched = False

            for experience in experiences:

                role_title = (
                    experience.role.title
                    if experience.role
                    else None
                )

                if any(
                    _role_matches(
                        requested_role,
                        role_title,
                    )
                    for requested_role in roles
                ):
                    matched = True
                    break

            if matched:
                filtered.append(
                    candidate
                )

        candidates = filtered

    else:

        candidates = db.scalars(
            query
        ).all()

    # Filter by the candidate's explicitly stored location.
    if location:
        candidates = [
            candidate
            for candidate in candidates
            if location_matches(location, candidate.location)
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

            if min_experience is not None and (
                total_years < float(min_experience)
                or (requirements.get("min_experience_exclusive")
                    and total_years <= float(min_experience))
            ):
                continue

            if (
                max_experience is not None
                and total_years > float(
                    max_experience
                )
            ):
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

    unique_requirements = list(dict.fromkeys(
        requirement.strip()
        for requirement in semantic_requirements
        if requirement and requirement.strip()
    ))
    requirements = [
        {
            "evidence_query": _expand_semantic_query(requirement),
            "value": requirement,
            "target": "",
            "type": "OTHER",
        }
        for requirement in unique_requirements
    ]

    if not requirements:
        return []

    # Retrieve each clause independently. A single "A and B" embedding can
    # miss candidates whose evidence for A and B lives in different resume
    # sections; qualification below still requires every mandatory clause.
    per_requirement_limit = max(20, math.ceil(limit / len(requirements)))
    evidence_by_key: dict[tuple[str, str], dict] = {}

    for requirement in requirements:
        requirement_text = str(requirement["value"])
        hits = retrieve_semantic_candidates(
            query=requirement["evidence_query"],
            limit=per_requirement_limit,
            candidate_ids=candidate_ids,
            requirements=[requirement],
        )
        for item in hits:
            evidence_id = item.get("evidence_id") or item.get("source_id")
            text_key = " ".join(str(item.get("text") or "").casefold().split())
            evidence_key = str(evidence_id) if evidence_id is not None else f"{item.get('candidate_id')}:{text_key}"
            key = (evidence_key, _normalize(requirement_text))
            existing = evidence_by_key.get(key)
            if existing is None:
                existing = {
                    **item,
                    "retrieval_requirements": [requirement_text],
                    "reranker_query": requirement_text,
                }
                evidence_by_key[key] = existing
            else:
                item_score = float(item.get("retrieval_score") or 0.0)
                existing["retrieval_score"] = float(existing.get("retrieval_score") or 0.0) + item_score
                for source in item.get("retrieval_sources", []):
                    if source not in existing.setdefault("retrieval_sources", []):
                        existing["retrieval_sources"].append(source)

    merged_evidence = list(evidence_by_key.values())
    return sorted(
        merged_evidence,
        key=lambda item: float(item.get("retrieval_score") or 0.0),
        reverse=True,
    )[:limit]


def _expand_semantic_query(requirement: str) -> str:
    return expand_semantic_requirement(requirement)

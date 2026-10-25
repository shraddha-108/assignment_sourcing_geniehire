from datetime import date, timedelta
import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from qdrant_client import models

from models import Candidate, CandidateSkill, Experience
from ingestion.vectorDB.embedder import embed_text
from ingestion.vectorDB.qdrant_client import (
    client,
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
)

SEMANTIC_RETRIEVAL_LIMIT = int(
    os.getenv(
        "SEMANTIC_RETRIEVAL_LIMIT",
        "200",
    )
)

def _parse_date(value):
    if value is None:
        return None

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        try:
            return date.fromisoformat(
                value[:10]
            )
        except ValueError:
            return None

    return None

def _cutoff_date(
    recency_months: int,
) -> date:

    return (
        date.today()
        - timedelta(
            days=recency_months * 30
        )
    )

def _experience_is_recent(
    start_date,
    end_date,
    cutoff_date: date,
) -> bool:

    parsed_start_date = _parse_date(
        start_date
    )

    parsed_end_date = _parse_date(
        end_date
    )

    if parsed_start_date is None:
        return False

    # A missing end date means the experience has
    # no known end date. We do not use it as proof
    # of recency unless the experience has started
    # within the requested recency window.
    if parsed_end_date is None:
        return (
            parsed_start_date <= date.today()
            and date.today() >= cutoff_date
        )

    return parsed_end_date >= cutoff_date

def _role_matches_title(
    role: str,
    title: str | None,
) -> bool:
    """
    Match a structured role against an actual experience title.

    This is intentionally lexical, not semantic. Semantic equivalence such as
    "Backend Engineer" vs "Backend Developer" belongs to the semantic layer.
    Here we only want a reliable structured match without accidental substring
    matches such as "ai" matching an unrelated word containing those letters.
    """
    if not role or not title:
        return False

    import re

    role_tokens = re.findall(r"[a-z0-9]+(?:[+#][a-z0-9]+)?", role.lower())
    title_tokens = set(
        re.findall(r"[a-z0-9]+(?:[+#][a-z0-9]+)?", title.lower())
    )

    if not role_tokens:
        return False

    return all(token in title_tokens for token in role_tokens)


def retrieve_structured_candidates(
    db: Session,
    requirements: dict,
) -> list[dict]:
    """
    Retrieve candidates using only the structured requirements supplied by
    query understanding.

    Important contract:
      - A requirement source is only joined/filtered when that source is
        actually required.
      - CandidateSkill is never made mandatory for experience-only or role-only
        searches.
      - Structured retrieval performs deterministic eligibility filtering for
        structured fields; semantic equivalence is handled downstream.
      - The returned shape remains compatible with the existing pipeline:
        every row contains candidate plus optional skill metadata.
    """
    skills = requirements.get("skills") or []
    role = requirements.get("role")
    recency_months = requirements.get("recency_months")
    recency_scope = requirements.get("recency_scope")
    experience_min_years = requirements.get("experience_min_years")
    experience_scope = requirements.get("experience_scope")

    normalized_skills = sorted(
        {
            str(skill).strip().lower()
            for skill in skills
            if str(skill).strip()
        }
    )

    minimum_experience_months = None
    if experience_min_years is not None:
        try:
            minimum_experience_months = float(experience_min_years) * 12
        except (TypeError, ValueError):
            minimum_experience_months = None

    # ---------------------------------------------------------------
    # Candidate-level filters
    # ---------------------------------------------------------------
    candidate_conditions = []

    if minimum_experience_months is not None and experience_scope != "SKILL":
        candidate_conditions.append(
            Candidate.total_experience_months >= minimum_experience_months
        )

    role_candidate_ids = None
    if role:
        # Role is deliberately lexical in the structured layer. Do not invent
        # semantic synonyms here; semantic retrieval/validation owns that job.
        role_candidates = db.execute(
            select(Experience.candidate_id)
            .where(Experience.title.is_not(None))
            .distinct()
        ).scalars().all()

        if not role_candidates:
            return []

        experiences = (
            db.query(Experience)
            .filter(Experience.candidate_id.in_(role_candidates))
            .all()
        )

        role_candidate_ids = {
            experience.candidate_id
            for experience in experiences
            if _role_matches_title(role, experience.title)
        }

        if not role_candidate_ids:
            return []

        candidate_conditions.append(Candidate.id.in_(role_candidate_ids))

    # ---------------------------------------------------------------
    # No skill requirement: do NOT join CandidateSkill.
    # ---------------------------------------------------------------
    if not normalized_skills:
        stmt = select(Candidate)
        if candidate_conditions:
            stmt = stmt.where(*candidate_conditions)

        candidates = db.execute(stmt).scalars().all()
        return [
            {
                "candidate": candidate,
                "skill": None,
                "last_used_date": None,
                "total_months": None,
            }
            for candidate in candidates
        ]

    # ---------------------------------------------------------------
    # Skill requirement: CandidateSkill is now intentionally required.
    # ---------------------------------------------------------------
    matching_candidates = (
        select(CandidateSkill.candidate_id)
        .where(
            func.lower(CandidateSkill.skill).in_(normalized_skills)
        )
        .group_by(CandidateSkill.candidate_id)
        .having(
            func.count(func.distinct(func.lower(CandidateSkill.skill)))
            == len(normalized_skills)
        )
        .subquery()
    )

    stmt = (
        select(Candidate, CandidateSkill)
        .join(
            CandidateSkill,
            Candidate.id == CandidateSkill.candidate_id,
        )
        .where(
            Candidate.id.in_(select(matching_candidates.c.candidate_id)),
            func.lower(CandidateSkill.skill).in_(normalized_skills),
        )
    )

    if candidate_conditions:
        stmt = stmt.where(*candidate_conditions)

    # Skill-specific experience belongs to CandidateSkill. Overall experience
    # was already applied to Candidate above.
    if (
        minimum_experience_months is not None
        and experience_scope == "SKILL"
    ):
        stmt = stmt.where(
            CandidateSkill.total_months >= minimum_experience_months
        )

    # Structured recency is only a skill recency requirement. Semantic recency
    # must remain available to the semantic validator instead of becoming an
    # accidental CandidateSkill filter.
    if (
        recency_months is not None
        and (recency_scope is None or recency_scope == "SKILL")
    ):
        try:
            cutoff_date = _cutoff_date(int(recency_months))
        except (TypeError, ValueError):
            cutoff_date = None

        if cutoff_date is not None:
            stmt = stmt.where(
                CandidateSkill.last_used_date >= cutoff_date
            )

    rows = db.execute(stmt).all()

    return [
        {
            "candidate": candidate,
            "skill": skill.skill,
            "last_used_date": skill.last_used_date,
            "total_months": skill.total_months,
        }
        for candidate, skill in rows
    ]


def _semantic_requirement_query(requirement: dict) -> str:
    """Build a semantic retrieval phrase that preserves requirement target context."""
    base = str(
        requirement.get("evidence_query")
        or requirement.get("value")
        or ""
    ).strip()
    target = str(requirement.get("target") or "").strip()

    if not base:
        return target
    if not target:
        return base

    normalized_base = " ".join(base.lower().split())
    normalized_target = " ".join(target.lower().split())
    if normalized_target in normalized_base:
        return base

    return f"{base} {target}".strip()

def _semantic_query_variants_with_requirements(
    query: str,
    requirements: list[dict] | None,
) -> list[tuple[str, tuple[int, ...], int]]:
    """
    Build high-recall semantic retrieval formulations while preserving
    requirement provenance and query specificity.

    Retrieval is intentionally permissive. It is not allowed to decide
    whether a candidate satisfies a recruiter requirement; that decision
    belongs to downstream qualification.

    The important distinction here is between:
      - discovery queries: broad formulations that maximize recall
      - relationship queries: formulations that preserve the relationship
        between requirement components
      - component queries: individual semantic anchors such as an activity
        or target, useful when the candidate's resume expresses the same
        concept with different wording

    No domain-specific vocabulary or query-specific rules are used. The
    structured requirement produced by query understanding is the source
    of the retrieval formulations.
    """
    variants: list[tuple[str, tuple[int, ...], int]] = []

    def add(
        value,
        requirement_ids=(),
        strength: int = 0,
    ) -> None:
        value = str(value or "").strip()
        if not value:
            return

        normalized = " ".join(value.lower().split())
        if not normalized:
            return

        normalized_ids = tuple(
            sorted(
                {
                    int(requirement_id)
                    for requirement_id in requirement_ids
                }
            )
        )

        for index, (
            existing,
            existing_ids,
            existing_strength,
        ) in enumerate(variants):
            if " ".join(existing.lower().split()) != normalized:
                continue

            variants[index] = (
                existing,
                tuple(
                    sorted(
                        set(existing_ids).union(normalized_ids)
                    )
                ),
                max(existing_strength, strength),
            )
            return

        variants.append(
            (
                value,
                normalized_ids,
                strength,
            )
        )

    requirement_list = requirements or []

    # The original recruiter query is useful for broad discovery, but it
    # must not be treated as evidence for every individual requirement.
    add(query, strength=0)

    for requirement_index, requirement in enumerate(requirement_list):
        if not isinstance(requirement, dict):
            continue

        requirement_ids = (requirement_index,)
        requirement_type = str(
            requirement.get("type", "") or ""
        ).upper()

        value = str(
            requirement.get("value") or ""
        ).strip()

        evidence_query = str(
            requirement.get("evidence_query") or ""
        ).strip()

        target = str(
            requirement.get("target") or ""
        ).strip()

        requirement_query = _semantic_requirement_query(
            requirement
        )

        # The strongest retrieval formulation is the complete semantic
        # relationship represented by the requirement.
        add(
            requirement_query,
            requirement_ids,
            strength=4,
        )

        # If query understanding supplied an explicit evidence formulation,
        # use it as another high-quality semantic formulation.
        add(
            evidence_query,
            requirement_ids,
            strength=4,
        )

        if requirement_type == "ACTIVITY":
            # Activity-only retrieval improves recall when the resume uses
            # different wording for the target relationship.
            add(
                value,
                requirement_ids,
                strength=2,
            )

            # Target-only retrieval is deliberately allowed as a discovery
            # path. It can surface evidence whose wording differs radically
            # from the recruiter's wording. The validator must still prove
            # the activity and relationship before the candidate can match.
            add(
                target,
                requirement_ids,
                strength=1,
            )

            if value and target:
                # Preserve the relationship explicitly in several natural
                # formulations. These are generated from the structured
                # requirement rather than from domain-specific synonyms.
                relationship_forms = (
                    f"{value} using {target}",
                    f"{value} with {target}",
                    f"experience involving {value} and {target}",
                )

                for formulation in relationship_forms:
                    add(
                        formulation,
                        requirement_ids,
                        strength=3,
                    )
            elif value:
                add(
                    f"candidate experience involving {value}",
                    requirement_ids,
                    strength=3,
                )
                add(
                    f"professional work involving {value}",
                    requirement_ids,
                    strength=3,
                )
                add(
                    f"projects involving {value}",
                    requirement_ids,
                    strength=3,
                )

            if target:
                add(
                    f"candidate experience involving {target}",
                    requirement_ids,
                    strength=1,
                )
                add(
                    f"professional work involving {target}",
                    requirement_ids,
                    strength=1,
                )

        elif requirement_type == "INDUSTRY":
            add(
                value,
                requirement_ids,
                strength=2,
            )
            add(
                target,
                requirement_ids,
                strength=2,
            )

            industry_value = (
                value
                or evidence_query
                or target
            )
            if industry_value:
                add(
                    f"industry experience in {industry_value}",
                    requirement_ids,
                    strength=3,
                )
                add(
                    f"professional experience in {industry_value}",
                    requirement_ids,
                    strength=3,
                )

        elif requirement_type == "OTHER":
            add(
                value,
                requirement_ids,
                strength=2,
            )
            add(
                target,
                requirement_ids,
                strength=1,
            )

            other_value = (
                evidence_query
                or value
                or target
            )
            if other_value:
                add(
                    f"professional experience related to {other_value}",
                    requirement_ids,
                    strength=3,
                )

        else:
            # For future semantic requirement types, retain the same generic
            # high-recall behavior without requiring a new domain-specific
            # branch.
            add(
                value,
                requirement_ids,
                strength=2,
            )
            add(
                target,
                requirement_ids,
                strength=1,
            )

    return variants

def _semantic_query_variants(
    query: str,
    requirements: list[dict] | None,
) -> list[str]:
    """Backward-compatible query-only view of semantic variants."""
    return [
        variant
        for variant, _, _ in _semantic_query_variants_with_requirements(
            query,
            requirements,
        )
    ]

def _query_semantic_points(
    query: str,
    limit: int,
    query_filter,
):
    dense_query = embed_text(
        query
    )

    return client.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=[
            models.Prefetch(
                query=dense_query,
                using=DENSE_VECTOR_NAME,
                limit=limit,
                filter=query_filter,
            ),
            models.Prefetch(
                query=models.Document(
                    text=query,
                    model="Qdrant/bm25",
                ),
                using=SPARSE_VECTOR_NAME,
                limit=limit,
                filter=query_filter,
            ),
        ],
        query=models.FusionQuery(
            fusion=models.Fusion.RRF
        ),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

def retrieve_semantic_candidates(
    query: str,
    limit: int = SEMANTIC_RETRIEVAL_LIMIT,
    candidate_ids: list[int] | None = None,
    recency_months: int | None = None,
    requirements: list[dict] | None = None,
    min_retrieval_score: float | None = None,
) -> list[dict]:
    """
    Retrieve semantic evidence broadly.

    This function is a discovery layer only.

    It must not decide whether a candidate qualifies for a
    recruiter requirement. Qualification happens downstream
    in the validator.

    Dense + sparse retrieval are combined through Qdrant RRF.
    Multiple query formulations are used to improve recall.
    """

    semantic_requirements = (
        requirements or []
    )

    query_variants = _semantic_query_variants_with_requirements(
        query,
        semantic_requirements,
    )

    if not query_variants:
        return []

    filter_conditions = []

    if candidate_ids:
        filter_conditions.append(
            models.FieldCondition(
                key="candidate_id",
                match=models.MatchAny(
                    any=candidate_ids
                ),
            )
        )

    query_filter = (
        models.Filter(
            must=filter_conditions
        )
        if filter_conditions
        else None
    )

    # Semantic recency is deliberately not used
    # as a Qdrant filter.
    #
    # The retrieved evidence must first be available
    # to the validator so it can determine whether the
    # relevant evidence itself is recent.
    if recency_months is not None:
        _ = _cutoff_date(
            recency_months
        )

    # Keep the argument for backward compatibility,
    # but do not use a default retrieval-score floor.
    #
    # Qdrant RRF scores are rank-fusion scores rather
    # than cosine similarities. A hard absolute floor
    # can silently remove potentially valid evidence.
    #
    # Qualification belongs downstream.
    retrieval_score_threshold = (
        None
        if min_retrieval_score is None
        else float(
            min_retrieval_score
        )
    )

    merged: dict[
        tuple,
        dict,
    ] = {}

    for (
        query_variant,
        requirement_ids,
        query_strength,
    ) in query_variants:
        response = _query_semantic_points(
            query_variant,
            limit,
            query_filter,
        )

        for point in response.points:

            payload = point.payload or {}

            if payload.get(
                "chunk_type"
            ) == "education":
                continue

            candidate_id = payload.get(
                "candidate_id"
            )

            chunk_id = payload.get(
                "chunk_id"
            )

            text = payload.get(
                "text",
                "",
            )

            if (
                candidate_id is None
                or not text
            ):
                continue

            retrieval_score = float(
                point.score
            )

            if (
                retrieval_score_threshold
                is not None
                and retrieval_score
                < retrieval_score_threshold
            ):
                continue

            evidence_key = (
                candidate_id,
                chunk_id,
                text,
            )

            existing = merged.get(
                evidence_key
            )

            if existing is not None:

                existing[
                    "retrieval_score"
                ] = max(
                    float(
                        existing.get(
                            "retrieval_score",
                            0.0,
                        )
                    ),
                    retrieval_score,
                )

                if (
                    query_variant
                    not in existing[
                        "retrieval_queries"
                    ]
                ):
                    existing[
                        "retrieval_queries"
                    ].append(
                        query_variant
                    )

                existing[
                    "retrieval_query_strength"
                ] = max(
                    int(
                        existing.get(
                            "retrieval_query_strength",
                            0,
                        )
                    ),
                    query_strength,
                )

                existing[
                    "matched_requirement_ids"
                ] = sorted(
                    set(existing.get("matched_requirement_ids", []))
                    .union(requirement_ids)
                )

                continue

            merged[
                evidence_key
            ] = {
                "candidate_id": candidate_id,
                "chunk_id": chunk_id,
                "chunk_type": payload.get(
                    "chunk_type"
                ),
                "section": payload.get(
                    "section"
                ),
                "text": text,
                "company": payload.get(
                    "company"
                ),
                "job_title": payload.get(
                    "job_title"
                ),
                "start_date": payload.get(
                    "start_date"
                ),
                "end_date": payload.get(
                    "end_date"
                ),
                "project_title": payload.get(
                    "project_title"
                ),
                "requirements": semantic_requirements,
                "matched_requirement_ids": list(requirement_ids),
                "retrieval_score": retrieval_score,
                "retrieval_query_strength": query_strength,
                "retrieval_queries": [
                    query_variant
                ],
            }

    results = list(
        merged.values()
    )

    results.sort(
        key=lambda item: (
            int(
                item.get(
                    "retrieval_query_strength",
                    0,
                )
            ),
            float(
                item.get(
                    "retrieval_score",
                    0.0,
                )
            ),
            len(
                item.get(
                    "retrieval_queries",
                    [],
                )
            ),
        ),
        reverse=True,
    )

    return results

def consolidate_candidate_evidence(
    evidence: list[dict],
    max_chunks_per_candidate: int = 3,
) -> list[dict]:
    """Consolidate evidence while preserving requirement coverage."""
    grouped: dict[int, list[dict]] = {}

    for item in evidence:
        candidate_id = item.get("candidate_id")
        if candidate_id is None:
            continue
        grouped.setdefault(candidate_id, []).append(item)

    candidates = []

    for candidate_id, chunks in grouped.items():
        chunks.sort(
            key=lambda item: (
                float(
                    item.get(
                        "reranker_score",
                        item.get("retrieval_score", 0),
                    )
                ),
                int(
                    item.get(
                        "retrieval_query_strength",
                        0,
                    )
                ),
            ),
            reverse=True,
        )

        selected: list[dict] = []
        seen_text: set[str] = set()
        covered_requirements: set[int] = set()

        def select_chunk(chunk: dict) -> bool:
            normalized_text = " ".join(chunk.get("text", "").lower().split())
            if not normalized_text or normalized_text in seen_text:
                return False
            selected.append(chunk)
            seen_text.add(normalized_text)
            for requirement_id in chunk.get("matched_requirement_ids", []):
                try:
                    covered_requirements.add(int(requirement_id))
                except (TypeError, ValueError):
                    continue
            return True

        requirement_ids = sorted(
            {
                int(requirement_id)
                for chunk in chunks
                for requirement_id in chunk.get("matched_requirement_ids", [])
                if str(requirement_id).isdigit()
            }
        )

        # First guarantee requirement coverage, but respect the evidence budget.
        # If there are more represented requirements than the budget allows,
        # prioritize the strongest chunks that cover the largest number of
        # still-uncovered requirements.
        remaining_requirement_ids = set(requirement_ids)
        while remaining_requirement_ids and len(selected) < max_chunks_per_candidate:
            best_chunk = None
            best_new_requirements = set()
            best_key = None

            for chunk in chunks:
                normalized_text = " ".join(chunk.get("text", "").lower().split())
                if not normalized_text or normalized_text in seen_text:
                    continue

                chunk_requirement_ids = {
                    int(value)
                    for value in chunk.get("matched_requirement_ids", [])
                    if str(value).isdigit()
                }
                new_requirements = chunk_requirement_ids.intersection(
                    remaining_requirement_ids
                )
                if not new_requirements:
                    continue

                score = float(
                    chunk.get(
                        "reranker_score",
                        chunk.get("retrieval_score", 0),
                    )
                )
                key = (
                    len(new_requirements),
                    score,
                    int(
                        chunk.get(
                            "retrieval_query_strength",
                            0,
                        )
                    ),
                )

                if best_key is None or key > best_key:
                    best_key = key
                    best_chunk = chunk
                    best_new_requirements = new_requirements

            if best_chunk is None:
                break

            select_chunk(best_chunk)
            remaining_requirement_ids.difference_update(best_new_requirements)

        # Then fill the remaining evidence budget with the strongest chunks.
        for chunk in chunks:
            if len(selected) >= max_chunks_per_candidate:
                break
            select_chunk(chunk)

        if not selected:
            continue

        reranker_scores = [
            float(item.get("reranker_score", item.get("retrieval_score", 0)))
            for item in selected
        ]

        candidates.append(
            {
                "candidate_id": candidate_id,
                "evidence": selected,
                "reranker_score": max(reranker_scores),
                "matched_requirement_ids": sorted(covered_requirements),
            }
        )

    candidates.sort(
        key=lambda candidate: candidate["reranker_score"],
        reverse=True,
    )
    return candidates

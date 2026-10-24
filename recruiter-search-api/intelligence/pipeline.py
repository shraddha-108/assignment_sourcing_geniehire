import os
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.retriever import (
    retrieve_structured_candidates,
    retrieve_semantic_candidates,
    consolidate_candidate_evidence,
)

from intelligence.reranker import (
    rerank_evidence,
)

from intelligence.scorer import (
    score_candidates,
)

from intelligence.ranker import (
    rank_candidates,
)

from intelligence.validator import (
    validate_semantic_requirements,
)

from models import Candidate, Experience


RERANKER_MIN_SCORE = float(
    os.getenv(
        "RERANKER_MIN_SCORE",
        "-4.0",
    )
)

FINAL_SEMANTIC_SCORE_MIN = float(
    os.getenv(
        "FINAL_SEMANTIC_SCORE_MIN",
        "-4.0",
    )
)

# The CrossEncoder score is a relevance signal, not a qualification
# decision. Semantic validation may need to inspect evidence that has a
# weaker reranker score but still contains the evidence required by the
# query.
#
# Keep this lower than RERANKER_MIN_SCORE so potentially valid evidence
# reaches the deterministic semantic validator. The final candidate
# decision still uses FINAL_SEMANTIC_SCORE_MIN after validation.
SEMANTIC_VALIDATION_EVIDENCE_MIN_SCORE = float(
    os.getenv(
        "SEMANTIC_VALIDATION_EVIDENCE_MIN_SCORE",
        "-10.0",
    )
)


def _prepare_structured_candidates_for_scoring(
    candidates: list[dict],
    requirements: dict,
) -> list[dict]:
    """
    Prepare structured rows for candidate-level scoring.

    The structured retriever returns one row per CandidateSkill. That is
    useful for discovery, but it must not become one result per skill.
    When experience is an overall candidate requirement, score against the
    candidate's total experience rather than whichever skill row happened to
    be selected.
    """
    experience_min_years = requirements.get(
        "experience_min_years"
    )
    experience_scope = requirements.get(
        "experience_scope"
    )

    if (
        experience_min_years is None
        or experience_scope == "SKILL"
    ):
        return candidates

    prepared = []

    for item in candidates:
        candidate = item.get("candidate")
        prepared_item = dict(item)

        prepared_item["total_months"] = int(
            getattr(
                candidate,
                "total_experience_months",
                0,
            )
            or 0
        )

        prepared.append(prepared_item)

    return prepared


def _consolidate_structured_results(
    scored_candidates: list[dict],
    requirements: dict,
) -> list[dict]:
    """
    Collapse CandidateSkill rows into exactly one result per candidate.

    Structured retrieval intentionally returns one row for every matching
    skill. The recruiter-facing result, however, represents a candidate, not
    a candidate-skill pair. This function groups those rows by candidate ID,
    preserves the strongest scoring row, and exposes all matching skills as
    metadata without creating duplicate candidate cards.
    """
    grouped: dict[int, list[dict]] = {}

    for item in scored_candidates:
        candidate = item.get("candidate")
        candidate_id = getattr(
            candidate,
            "id",
            None,
        )

        if candidate_id is None:
            continue

        grouped.setdefault(
            candidate_id,
            [],
        ).append(item)

    consolidated = []
    requested_skills = requirements.get("skills") or []

    for candidate_id, items in grouped.items():
        items.sort(
            key=lambda item: float(
                item.get("score", 0.0)
            ),
            reverse=True,
        )

        best = dict(items[0])

        if requested_skills:
            matched_skills = []

            for item in items:
                skill = item.get("skill")
                if not skill:
                    continue

                if skill not in matched_skills:
                    matched_skills.append(skill)

            best["matched_skills"] = matched_skills
        else:
            best["matched_skills"] = []

        # Keep the candidate-level score from the strongest matching row.
        # The row itself is retained only as compatibility metadata; the
        # result is now one object per unique candidate.
        consolidated.append(best)

    consolidated.sort(
        key=lambda item: float(
            item.get("score", 0.0)
        ),
        reverse=True,
    )

    return consolidated


def execute_structured_search(
    db: Session,
    requirements: dict,
    requested_count: int,
    count_explicit: bool,
) -> list[dict]:

    candidates = retrieve_structured_candidates(
        db,
        requirements,
    )

    candidates = _prepare_structured_candidates_for_scoring(
        candidates,
        requirements,
    )

    scored_candidates = score_candidates(
        candidates,
        requirements,
    )

    consolidated_candidates = _consolidate_structured_results(
        scored_candidates,
        requirements,
    )

    results = rank_candidates(
        consolidated_candidates,
        requested_count,
        count_explicit,
    )

    for result in results:
        result["match_status"] = "MATCH"
        result["match_score"] = round(
            float(result.get("score", 0)),
            1,
        )

    return results


def execute_semantic_search(
    db: Session,
    query: str,
    requested_count: int,
    count_explicit: bool,
    requirements: list[dict] | dict | None = None,
) -> list[dict]:

    retrieval_limit = max(
        requested_count * 10,
        100,
    )

    recency_months = None

    # Backward compatibility:
    # Older callers may still pass the legacy structured
    # requirements dictionary.
    #
    # The new classifier produces a list of requirement
    # objects. When that list is available, pass the entire
    # requirement context to the retriever.
    if isinstance(requirements, dict):

        recency_scope = requirements.get(
            "recency_scope"
        )

        if recency_scope == "SEMANTIC":

            recency_months = requirements.get(
                "recency_months"
            )

        semantic_requirements = [
            requirements
        ]

    elif isinstance(requirements, list):

        semantic_requirements = requirements

        # Backward-compatible extraction of recency
        # from the new requirement representation.
        for requirement in semantic_requirements:

            if not isinstance(
                requirement,
                dict,
            ):
                continue

            if (
                requirement.get(
                    "recency_months"
                )
                is not None
            ):

                recency_months = requirement.get(
                    "recency_months"
                )

                break

    else:

        semantic_requirements = []

    evidence = retrieve_semantic_candidates(
        query=query,
        limit=retrieval_limit,
        recency_months=recency_months,
        requirements=semantic_requirements,
    )

    return _build_semantic_results(
        db=db,
        query=query,
        evidence=evidence,
        requested_count=requested_count,
        count_explicit=count_explicit,
        semantic_requirements=semantic_requirements,
    )


def execute_hybrid_search(
    db: Session,
    requirements: dict,
    semantic_query: str,
    requested_count: int,
    count_explicit: bool,
    semantic_requirements: list[dict] | None = None,
) -> list[dict]:

    structured_candidates = (
        retrieve_structured_candidates(
            db,
            requirements,
        )
    )

    if not structured_candidates:
        return []

    candidate_ids = list(
        {
            item["candidate"].id
            for item in structured_candidates
        }
    )

    retrieval_limit = max(
        requested_count * 10,
        100,
    )

    recency_months = None

    # New requirement representation.
    #
    # The semantic requirement list is kept separate from
    # structured requirements because recency can belong to
    # the semantic activity/project requirement rather than
    # to the structured skill.
    if semantic_requirements:

        for requirement in semantic_requirements:

            if not isinstance(
                requirement,
                dict,
            ):
                continue

            requirement_recency = requirement.get(
                "recency_months"
            )

            if requirement_recency is not None:

                recency_months = (
                    requirement_recency
                )

                break

    # Backward compatibility with the old classifier.
    if (
        recency_months is None
        and requirements.get(
            "recency_scope"
        )
        == "SEMANTIC"
    ):

        recency_months = requirements.get(
            "recency_months"
        )

    evidence = retrieve_semantic_candidates(
        query=semantic_query,
        limit=retrieval_limit,
        candidate_ids=candidate_ids,
        recency_months=recency_months,
        requirements=semantic_requirements,
    )

    if not evidence:
        return []

    structured_map = {}

    for item in structured_candidates:

        candidate_id = item[
            "candidate"
        ].id

        structured_map.setdefault(
            candidate_id,
            [],
        ).append(item)

    return _build_semantic_results(
        db=db,
        query=semantic_query,
        evidence=evidence,
        requested_count=requested_count,
        count_explicit=count_explicit,
        structured_map=structured_map,
        semantic_requirements=semantic_requirements or [],
    )


def _build_semantic_results(
    db: Session,
    query: str,
    evidence: list[dict],
    requested_count: int,
    count_explicit: bool,
    structured_map: dict | None = None,
    semantic_requirements: list[dict] | None = None,
) -> list[dict]:

    if not evidence:
        return []

    # ---------------------------------------------------------
    # STEP 1
    # Qdrant gives us evidence chunks.
    #
    # Retrieval finds potentially relevant evidence.
    # It does NOT decide whether every requirement is
    # actually proven.
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # STEP 2
    # CrossEncoder reranks the individual evidence chunks.
    #
    # This is a relevance signal.
    # It is NOT a qualification percentage.
    # ---------------------------------------------------------

    reranked_evidence = rerank_evidence(
        query=query,
        evidence=evidence,
    )

    if not reranked_evidence:
        return []

    # Stage 2 evidence floor:
    #
    # Do not use the stricter candidate/ranking threshold here.
    # A CrossEncoder score is only a relevance signal, and a valid
    # requirement-specific evidence chunk can score below
    # RERANKER_MIN_SCORE even when it is the evidence that proves the
    # requested activity.
    #
    # Keep a wider evidence pool for deterministic semantic validation.
    # The final candidate gate is still applied after validation.
    reranked_evidence = [
        item
        for item in reranked_evidence
        if float(item.get("reranker_score", 0))
        >= SEMANTIC_VALIDATION_EVIDENCE_MIN_SCORE
    ]

    if not reranked_evidence:
        return []

    # ---------------------------------------------------------
    # STEP 3
    # Group the strongest evidence by candidate.
    # ---------------------------------------------------------

    consolidated_candidates = (
        consolidate_candidate_evidence(
            evidence=reranked_evidence,
            max_chunks_per_candidate=3,
        )
    )

    if not consolidated_candidates:
        return []

    # ---------------------------------------------------------
    # STEP 4
    # In hybrid search, the structured candidate set is a hard
    # requirement. A semantic result outside that set must not
    # appear.
    # ---------------------------------------------------------

    if structured_map is not None:

        consolidated_candidates = [
            item
            for item in consolidated_candidates
            if item["candidate_id"]
            in structured_map
        ]

        if not consolidated_candidates:
            return []

    candidate_ids = [
        item["candidate_id"]
        for item in consolidated_candidates
    ]

    candidates = db.scalars(
        select(Candidate).where(
            Candidate.id.in_(candidate_ids)
        )
    ).all()

    candidate_map = {
        candidate.id: candidate
        for candidate in candidates
    }

    results = []

    for item in consolidated_candidates:

        candidate = candidate_map.get(
            item["candidate_id"]
        )

        if candidate is None:
            continue

        selected_evidence = []

        for evidence_item in item[
            "evidence"
        ]:

            source = (
                evidence_item.get(
                    "section"
                )
                or evidence_item.get(
                    "chunk_type"
                )
                or "unknown"
            )

            retrieval_score = float(
                evidence_item.get(
                    "retrieval_score",
                    0,
                )
            )

            reranker_score = float(
                evidence_item.get(
                    "reranker_score",
                    0,
                )
            )

            selected_evidence.append(
                {
                    "source": source,
                    "text": evidence_item.get(
                        "text",
                        "",
                    ),
                    "retrieval_score": round(
                        retrieval_score,
                        6,
                    ),
                    "reranker_score": round(
                        reranker_score,
                        6,
                    ),
                    "company": evidence_item.get(
                        "company"
                    ),
                    "job_title": evidence_item.get(
                        "job_title"
                    ),
                    "start_date": evidence_item.get(
                        "start_date"
                    ),
                    "end_date": evidence_item.get(
                        "end_date"
                    ),
                    "project_title": evidence_item.get(
                        "project_title"
                    ),
                }
            )

        if not selected_evidence:
            continue

        # -----------------------------------------------------
        # STEP 5
        # Validate semantic requirements against the actual
        # evidence retrieved for this candidate.
        #
        # Retrieval/reranking says:
        #   "this evidence looks relevant."
        #
        # Validation says:
        #   "this evidence actually supports the requirement."
        #
        # Required semantic requirements must be MATCH.
        # -----------------------------------------------------

        semantic_validation = (
            validate_semantic_requirements(
                requirements=semantic_requirements or [],
                evidence=selected_evidence,
            )
        )

        if not semantic_validation["matched"]:
            # Do not allow semantic similarity to turn an
            # unqualified candidate into a final result.
            continue

        best_reranker_score = float(
            item.get(
                "reranker_score",
                0,
            )
        )

        # The CrossEncoder is a ranking signal, not a qualification gate.
        # Once deterministic requirement validation has returned MATCH,
        # a low raw CrossEncoder score must not discard the candidate.
        #
        # This is important for evidence such as project descriptions:
        # semantically valid project evidence can receive a negative
        # MS-MARCO score even when it clearly proves the requirement.
        validation_confidence = 0.0

        for validation_item in semantic_validation.get(
            "requirements",
            [],
        ):
            if validation_item.get("status") == "MATCH":
                validation_confidence = max(
                    validation_confidence,
                    float(
                        validation_item.get(
                            "confidence",
                            0.0,
                        )
                    ),
                )

        # Convert the raw CrossEncoder score into a bounded diagnostic
        # signal only for ordering. It is deliberately secondary to
        # deterministic validation confidence.
        reranker_signal = max(
            0.0,
            min(
                1.0,
                (
                    best_reranker_score
                    - SEMANTIC_VALIDATION_EVIDENCE_MIN_SCORE
                )
                / (
                    0.0
                    - SEMANTIC_VALIDATION_EVIDENCE_MIN_SCORE
                ),
            ),
        )

        final_match_score = round(
            (
                validation_confidence * 0.75
            )
            + (
                reranker_signal * 0.25
            ),
            3,
        )

        result = {
            "id": candidate.id,
            "name": candidate.name,
            "email": candidate.email,
            "match_status": "MATCH",

            # Keep the raw retrieval/reranking signals internally
            # for debugging and accuracy analysis.
            "retrieval_score": round(
                max(
                    (
                        float(
                            evidence_item.get(
                                "retrieval_score",
                                0,
                            )
                        )
                        for evidence_item in item[
                            "evidence"
                        ]
                    ),
                    default=0,
                ),
                6,
            ),

            "reranker_score": round(
                best_reranker_score,
                6,
            ),

            "validation_confidence": round(
                validation_confidence,
                3,
            ),

            "match_score": round(
                final_match_score * 100,
                1,
            ),

            "semantic_validation": (
                semantic_validation
            ),

            "evidence": selected_evidence,
        }

        if structured_map is not None:

            matched_skills = []

            for structured_item in structured_map.get(
                candidate.id,
                [],
            ):

                matched_skills.append(
                    {
                        "skill": structured_item[
                            "skill"
                        ],
                        "last_used": (
                            structured_item[
                                "last_used_date"
                            ].isoformat()
                            if structured_item[
                                "last_used_date"
                            ]
                            else "unknown"
                        ),
                        "total_months": structured_item[
                            "total_months"
                        ],
                    }
                )

            result[
                "matched_skills"
            ] = matched_skills

        results.append(result)

    # ---------------------------------------------------------
    # STEP 6
    # Ranking remains based on the CrossEncoder relevance
    # signal, but only after semantic validation.
    #
    # The signal is NOT exposed as a match percentage.
    # ---------------------------------------------------------

    results.sort(
        key=lambda item: (
            item.get("match_score", 0.0),
            item.get("validation_confidence", 0.0),
            item.get("reranker_score", -999.0),
        ),
        reverse=True,
    )

    # The requested count is a maximum, not a guarantee.
    # Candidates removed by requirement validation are not
    # replaced with invalid candidates.
    if count_explicit:
        results = results[
            :requested_count
        ]

    return results


def _normalize_skill(value: str) -> str:
    return re.sub(
        r"[^a-z0-9+#.]+",
        " ",
        str(value or "").lower(),
    ).strip()


def _candidate_satisfies_structured_requirements(
    db: Session,
    candidate_id: int,
    requirements: dict,
    structured_map: dict,
    evidence: list[dict],
) -> bool:
    """
    Deterministically validate structured requirements for a candidate.

    Structured retrieval is used as strong evidence, but it is not the only
    possible source of truth. Semantic evidence can rescue a candidate when
    CandidateSkill is incomplete.
    """
    skills = requirements.get("skills") or []

    if skills:
        structured_items = structured_map.get(
            candidate_id,
            [],
        )

        structured_skills = {
            _normalize_skill(item.get("skill"))
            for item in structured_items
        }

        missing_skills = [
            skill
            for skill in skills
            if _normalize_skill(skill)
            not in structured_skills
        ]

        if missing_skills:
            evidence_text = " ".join(
                str(item.get("text", ""))
                for item in evidence
            ).lower()

            for skill in missing_skills:
                normalized = _normalize_skill(skill)

                if normalized not in _normalize_skill(
                    evidence_text
                ):
                    return False

    minimum_years = requirements.get(
        "experience_min_years"
    )

    if minimum_years is not None:
        candidate = db.get(
            Candidate,
            candidate_id,
        )

        if candidate is None:
            return False

        required_months = float(
            minimum_years
        ) * 12

        # Overall experience is checked from the candidate's structured
        # total when the recruiter did not explicitly scope experience
        # to a particular skill.
        if (
            candidate.total_experience_months
            is None
            or candidate.total_experience_months
            < required_months
        ):
            return False

    role = requirements.get("role")

    if role:
        requested_role_tokens = [
            token
            for token in str(role).lower().split()
            if token.strip()
        ]

        experiences = db.query(
            Experience
        ).filter(
            Experience.candidate_id
            == candidate_id
        ).all()

        role_match = False

        for experience in experiences:
            title = str(
                experience.title or ""
            ).lower()

            if requested_role_tokens and all(
                token in title
                for token in requested_role_tokens
            ):
                role_match = True
                break

        if not role_match:
            return False

    return True


def execute_unified_search(
    db: Session,
    query: str,
    structured_requirements: dict,
    semantic_query: str | None,
    requirements: list[dict] | None,
    requested_count: int,
    count_explicit: bool,
) -> tuple[list[dict], str]:
    """
    Unified natural-language retrieval.

    Structured and semantic retrieval are independent discovery channels.
    Neither channel is allowed to become a hard wall for the other.

    Acceptance is requirement-driven:
      1. retrieve broadly
      2. validate the actual evidence
      3. rank only validated candidates
      4. apply requested_count as a maximum
    """
    structured_candidates = retrieve_structured_candidates(
        db,
        structured_requirements,
    )

    structured_map = {}

    for item in structured_candidates:
        candidate_id = item[
            "candidate"
        ].id

        structured_map.setdefault(
            candidate_id,
            [],
        ).append(item)

    semantic_requirements = [
        requirement
        for requirement in (requirements or [])
        if isinstance(requirement, dict)
        and requirement.get("type")
        in {
            "ACTIVITY",
            "INDUSTRY",
            "OTHER",
        }
    ]

    semantic_results = []

    # Semantic retrieval is independent. It is never restricted to the
    # structured candidate IDs here.
    if semantic_requirements:
        semantic_text = (
            semantic_query
            or query
        )

        retrieval_limit = max(
            requested_count * 20,
            200,
        )

        recency_months = None

        for requirement in semantic_requirements:
            if requirement.get(
                "recency_months"
            ) is not None:
                recency_months = requirement.get(
                    "recency_months"
                )
                break

        semantic_evidence = retrieve_semantic_candidates(
            query=semantic_text,
            limit=retrieval_limit,
            recency_months=recency_months,
            requirements=semantic_requirements,
        )

        semantic_results = _build_semantic_results(
            db=db,
            query=semantic_text,
            evidence=semantic_evidence,
            requested_count=max(
                requested_count,
                1,
            ),
            count_explicit=False,
            structured_map=None,
            semantic_requirements=semantic_requirements,
        )

    # Pure structured search remains deterministic and cheap.
    if not semantic_requirements:
        structured_candidates = (
            _prepare_structured_candidates_for_scoring(
                structured_candidates,
                structured_requirements,
            )
        )

        scored_candidates = score_candidates(
            structured_candidates,
            structured_requirements,
        )

        consolidated_candidates = (
            _consolidate_structured_results(
                scored_candidates,
                structured_requirements,
            )
        )

        structured_results = rank_candidates(
            consolidated_candidates,
            requested_count,
            count_explicit,
        )

        for result in structured_results:
            result["match_status"] = "MATCH"
            result["match_score"] = round(
                float(result.get("score", 0)),
                1,
            )

        return (
            structured_results,
            "STRUCTURED",
        )

    # Semantic candidates are already requirement-validated. Now enforce
    # any independently structured claims (skill / role / experience)
    # without requiring the candidate to have been discovered by the
    # structured search.
    candidate_ids = [
        result["id"]
        for result in semantic_results
    ]

    candidates = db.scalars(
        select(Candidate).where(
            Candidate.id.in_(candidate_ids)
        )
    ).all()

    candidate_map = {
        candidate.id: candidate
        for candidate in candidates
    }

    final_results = []

    for result in semantic_results:
        candidate_id = result["id"]

        candidate = candidate_map.get(
            candidate_id
        )

        if candidate is None:
            continue

        if not _candidate_satisfies_structured_requirements(
            db=db,
            candidate_id=candidate_id,
            requirements=structured_requirements,
            structured_map=structured_map,
            evidence=result.get("evidence", []),
        ):
            continue

        final_results.append(result)

    # If the query contains both structured and semantic requirements,
    # report HYBRID. If it only contains semantic requirements, report
    # SEMANTIC.
    route = (
        "HYBRID"
        if structured_requirements.get("skills")
        or structured_requirements.get("role") is not None
        or structured_requirements.get(
            "experience_min_years"
        ) is not None
        else "SEMANTIC"
    )

    final_results.sort(
        key=lambda item: (
            item.get("match_score", 0.0),
            item.get("validation_confidence", 0.0),
            item.get("reranker_score", -999.0),
        ),
        reverse=True,
    )

    if count_explicit:
        final_results = final_results[
            :requested_count
        ]

    return (
        final_results,
        route,
    )

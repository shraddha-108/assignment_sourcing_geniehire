import os
import re
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.retriever import (
    retrieve_structured_candidates,
    retrieve_semantic_candidates,
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

from models import Candidate, CandidateSkill, Experience


def _log_timing(stage: str, started_at: float, **details) -> None:
    elapsed = time.perf_counter() - started_at

    detail_text = " ".join(
        f"{key}={value}"
        for key, value in details.items()
    )

    if detail_text:
        print(
            f"[SEARCH TIMING] {stage}: "
            f"{elapsed:.3f}s {detail_text}",
            flush=True,
        )
    else:
        print(
            f"[SEARCH TIMING] {stage}: "
            f"{elapsed:.3f}s",
            flush=True,
        )


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

    semantic_evaluation_query = _build_semantic_evaluation_query(
        semantic_requirements=semantic_requirements,
        fallback_query=query,
    )

    evidence = retrieve_semantic_candidates(
        query=semantic_evaluation_query,
        limit=retrieval_limit,
        recency_months=recency_months,
        requirements=semantic_requirements,
    )

    return _build_semantic_results(
        db=db,
        query=semantic_evaluation_query,
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

    semantic_evaluation_query = _build_semantic_evaluation_query(
        semantic_requirements=semantic_requirements or [],
        fallback_query=semantic_query,
    )

    evidence = retrieve_semantic_candidates(
        query=semantic_evaluation_query,
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
        query=semantic_evaluation_query,
        evidence=evidence,
        requested_count=requested_count,
        count_explicit=count_explicit,
        structured_map=structured_map,
        semantic_requirements=semantic_requirements or [],
        structured_requirements=requirements,
    )



def _normalize_evidence_tokens(value: str) -> set[str]:
    """Return normalized content tokens for generic evidence matching."""
    tokens = re.findall(
        r"[a-z0-9+#.]+",
        str(value or "").lower(),
    )
    return {
        token
        for token in tokens
        if len(token) > 2
    }


def _semantic_requirement_query_text(requirement: dict) -> str:
    """Build one complete semantic query from the requirement object.

    The complete relationship is kept intact so retrieval, reranking, and
    evidence selection all evaluate the same requirement instead of treating
    activity/value and target as unrelated pieces.
    """
    evidence_query = str(
        requirement.get("evidence_query") or ""
    ).strip()
    value = str(requirement.get("value") or "").strip()
    target = str(requirement.get("target") or "").strip()
    requirement_type = str(
        requirement.get("type") or ""
    ).upper()

    base = evidence_query or value or target
    if not base:
        return ""

    normalized_base = " ".join(base.lower().split())
    normalized_target = " ".join(target.lower().split())

    if not target or normalized_target in normalized_base:
        return base

    if requirement_type == "ACTIVITY":
        return f"{base} using {target}".strip()

    return f"{base} {target}".strip()


def _build_semantic_evaluation_query(
    semantic_requirements: list[dict] | None,
    fallback_query: str,
) -> str:
    """Build the query used by semantic reranking from full requirements."""
    requirement_queries = []

    for requirement in semantic_requirements or []:
        if not isinstance(requirement, dict):
            continue
        requirement_query = _semantic_requirement_query_text(
            requirement
        )
        if requirement_query:
            requirement_queries.append(requirement_query)

    if requirement_queries:
        return " and ".join(requirement_queries)

    return str(fallback_query or "").strip()


def _requirement_texts(requirement: dict) -> list[str]:
    """Build complete semantic representations for one requirement."""
    values = []

    complete_query = _semantic_requirement_query_text(requirement)
    if complete_query:
        values.append(complete_query)

    evidence_query = str(
        requirement.get("evidence_query") or ""
    ).strip()
    if evidence_query and evidence_query not in values:
        values.append(evidence_query)

    return values

def _build_semantic_retrieval_requirements(
    semantic_requirements: list[dict],
    structured_requirements: dict | None = None,
) -> list[dict]:
    """
    Build a generic retrieval requirement set for hybrid searches.

    Semantic requirements remain the requirements that the semantic
    validator must prove. Structured skills are added only as additional
    retrieval signals so that evidence mentioning those skills can reach
    the final structured validator.

    This is deliberately data-driven: the requested skills and semantic
    requirements come from the classifier; no query-specific terms are
    hardcoded here.
    """
    combined = [
        requirement
        for requirement in (semantic_requirements or [])
        if isinstance(requirement, dict)
    ]

    seen = {
        (
            str(requirement.get("type") or "").upper(),
            str(requirement.get("value") or "").strip().lower(),
        )
        for requirement in combined
    }

    for skill in (structured_requirements or {}).get("skills") or []:
        key = ("SKILL", str(skill).strip().lower())
        if not key[1] or key in seen:
            continue

        combined.append(
            {
                "type": "SKILL",
                "value": str(skill),
                "required": True,
                "evidence_query": f"worked with {skill}",
            }
        )
        seen.add(key)

    return combined


def _evidence_requirement_match_score(
    evidence_item: dict,
    requirement: dict,
) -> float:
    """Score evidence association without breaking semantic relationships.

    For relationship requirements such as activity + target, a target-only
    hit or activity-only hit is useful for discovery but is not sufficient to
    claim requirement coverage. The same evidence chunk, or the complete
    requirement-specific retrieval query that found it, must preserve the
    relationship.
    """
    complete_query = _semantic_requirement_query_text(requirement)
    if not complete_query:
        return 0.0

    requirement_type = str(
        requirement.get("type") or ""
    ).upper()
    value = str(requirement.get("value") or "").strip()
    target = str(requirement.get("target") or "").strip()

    complete_normalized = " ".join(complete_query.lower().split())
    complete_tokens = _normalize_evidence_tokens(complete_query)
    evidence_text = str(evidence_item.get("text") or "")
    evidence_normalized = " ".join(evidence_text.lower().split())
    evidence_tokens = _normalize_evidence_tokens(evidence_text)
    retrieval_queries = evidence_item.get("retrieval_queries") or []
    retrieval_strength = int(
        evidence_item.get("retrieval_query_strength", 0) or 0
    )

    if not complete_tokens:
        return 0.0

    # Relationship requirements need joint support. Component-only retrieval
    # remains available for recall, but it cannot satisfy the coverage gate.
    if requirement_type == "ACTIVITY" and value and target:
        value_tokens = _normalize_evidence_tokens(value)
        target_tokens = _normalize_evidence_tokens(target)

        for retrieval_query in retrieval_queries:
            query_normalized = " ".join(
                str(retrieval_query or "").lower().split()
            )
            query_tokens = _normalize_evidence_tokens(retrieval_query)
            if (
                complete_normalized
                and complete_normalized in query_normalized
            ):
                return 1.0
            if (
                value_tokens
                and target_tokens
                and value_tokens.issubset(query_tokens)
                and target_tokens.issubset(query_tokens)
            ):
                return max(0.95, min(1.0, retrieval_strength / 5.0))

        if (
            value_tokens
            and target_tokens
            and value_tokens.issubset(evidence_tokens)
            and target_tokens.issubset(evidence_tokens)
        ):
            return 0.85

        # A semantically strong reranker result can rescue a wording
        # mismatch such as "developed an AI chatbot" for a recruiter
        # request phrased as "built products with AI". This remains only
        # an evidence-selection signal; the validator must still prove the
        # activity/object/target relationship. Weak target-only evidence is
        # therefore not enough.
        try:
            reranker_score = float(
                evidence_item.get("reranker_score", -999.0)
            )
        except (TypeError, ValueError):
            reranker_score = -999.0

        target_present = bool(
            target_tokens and target_tokens.issubset(evidence_tokens)
        )
        if target_present and reranker_score >= float(
            os.getenv(
                "SEMANTIC_ACTIVITY_RELATION_RERANKER_MIN_SCORE",
                "-4.0",
            )
        ):
            return 0.6

        return 0.0

    if complete_normalized and complete_normalized in evidence_normalized:
        return 1.0

    if complete_normalized:
        for retrieval_query in retrieval_queries:
            query_normalized = " ".join(
                str(retrieval_query or "").lower().split()
            )
            if complete_normalized in query_normalized:
                return max(0.8, min(1.0, retrieval_strength / 5.0))

    if complete_tokens and evidence_tokens:
        return len(complete_tokens & evidence_tokens) / len(complete_tokens)

    return 0.0

def _consolidate_semantic_evidence(
    evidence: list[dict],
    semantic_requirements: list[dict],
    structured_requirements: dict | None = None,
) -> list[dict]:
    """
    Preserve evidence coverage for every required semantic requirement.

    The old consolidation selected only the globally strongest chunks per
    candidate. That can discard a valid chunk for a weaker requirement when
    a query contains several independent requirements. This function first
    selects the strongest available chunk for each requirement and then uses
    remaining capacity for the strongest overall evidence.

    No query-specific terms are used here. The requirement objects produced
    by the classifier drive the selection.
    """
    grouped: dict[int, list[dict]] = {}

    for item in evidence:
        candidate_id = item.get("candidate_id")
        if candidate_id is None:
            continue
        grouped.setdefault(candidate_id, []).append(item)

    required_semantic_requirements = [
        requirement
        for requirement in semantic_requirements
        if isinstance(requirement, dict)
        and requirement.get("required", True)
    ]

    retrieval_requirements = _build_semantic_retrieval_requirements(
        semantic_requirements=semantic_requirements,
        structured_requirements=structured_requirements,
    )

    coverage_requirements = [
        requirement
        for requirement in retrieval_requirements
        if isinstance(requirement, dict)
        and requirement.get("required", True)
    ]

    chunks_per_requirement = max(
        1,
        int(
            os.getenv(
                "SEMANTIC_EVIDENCE_CHUNKS_PER_REQUIREMENT",
                "2",
            )
        ),
    )
    base_chunks = max(
        1,
        int(
            os.getenv(
                "SEMANTIC_EVIDENCE_BASE_CHUNKS",
                "1",
            )
        ),
    )
    max_chunks = max(
        3,
        base_chunks
        + len(coverage_requirements) * chunks_per_requirement,
    )

    candidates = []

    for candidate_id, chunks in grouped.items():
        unique_chunks = []
        seen_text = set()

        for chunk in chunks:
            normalized_text = " ".join(
                str(chunk.get("text") or "").lower().split()
            )
            if not normalized_text or normalized_text in seen_text:
                continue
            seen_text.add(normalized_text)
            unique_chunks.append(chunk)

        if not unique_chunks:
            continue

        # A candidate can only be validated successfully if the retrieval
        # stage supplied at least some evidence associated with every hard
        # semantic requirement. This is a cheap recall-oriented prefilter,
        # not a qualification decision: the deterministic validator below
        # still decides whether the evidence truly proves each requirement.
        if coverage_requirements:
            missing_requirement = any(
                max(
                    (
                        _evidence_requirement_match_score(
                            chunk,
                            requirement,
                        )
                        for chunk in unique_chunks
                    ),
                    default=0.0,
                )
                <= 0
                for requirement in coverage_requirements
            )

            if missing_requirement:
                continue

        selected = []
        selected_keys = set()

        def add_chunk(chunk):
            key = " ".join(
                str(chunk.get("text") or "").lower().split()
            )
            if not key or key in selected_keys:
                return False
            selected_keys.add(key)
            selected.append(chunk)
            return True

        # Requirement coverage comes first. A chunk may cover more than one
        # requirement and is naturally reused instead of duplicated.
        for requirement in coverage_requirements:
            ranked_for_requirement = sorted(
                unique_chunks,
                key=lambda chunk: (
                    _evidence_requirement_match_score(
                        chunk,
                        requirement,
                    ),
                    int(
                        chunk.get("retrieval_query_strength", 0)
                    ),
                    float(chunk.get("reranker_score", 0.0)),
                    float(chunk.get("retrieval_score", 0.0)),
                ),
                reverse=True,
            )

            added = 0
            for chunk in ranked_for_requirement:
                match_score = _evidence_requirement_match_score(
                    chunk,
                    requirement,
                )
                if match_score <= 0:
                    continue
                if add_chunk(chunk):
                    added += 1
                if added >= chunks_per_requirement:
                    break

        # Fill remaining capacity with globally strong evidence.
        remaining = sorted(
            unique_chunks,
            key=lambda chunk: (
                int(
                    chunk.get("retrieval_query_strength", 0)
                ),
                float(chunk.get("reranker_score", 0.0)),
                float(chunk.get("retrieval_score", 0.0)),
            ),
            reverse=True,
        )

        for chunk in remaining:
            if len(selected) >= max_chunks:
                break
            add_chunk(chunk)

        if not selected:
            continue

        best_reranker_score = max(
            float(chunk.get("reranker_score", 0.0))
            for chunk in selected
        )

        candidates.append(
            {
                "candidate_id": candidate_id,
                "evidence": selected,
                "reranker_score": best_reranker_score,
            }
        )

    candidates.sort(
        key=lambda candidate: candidate["reranker_score"],
        reverse=True,
    )

    return candidates

def _build_semantic_results(
    db: Session,
    query: str,
    evidence: list[dict],
    requested_count: int,
    count_explicit: bool,
    structured_map: dict | None = None,
    semantic_requirements: list[dict] | None = None,
    structured_requirements: dict | None = None,
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

    stage_started_at = time.perf_counter()

    reranked_evidence = rerank_evidence(
        query=query,
        evidence=evidence,
    )

    _log_timing(
        "semantic.rerank_evidence",
        stage_started_at,
        evidence_in=len(evidence),
        evidence_out=len(reranked_evidence),
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

    stage_started_at = time.perf_counter()

    consolidated_candidates = _consolidate_semantic_evidence(
        evidence=reranked_evidence,
        semantic_requirements=semantic_requirements or [],
        structured_requirements=structured_requirements,
    )

    _log_timing(
        "semantic.consolidate_evidence",
        stage_started_at,
        evidence_in=len(reranked_evidence),
        candidates=len(consolidated_candidates),
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

    validation_started_at = time.perf_counter()

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
                    "retrieval_queries": list(
                        evidence_item.get(
                            "retrieval_queries",
                        )
                        or []
                    ),
                    "retrieval_query_strength": int(
                        evidence_item.get(
                            "retrieval_query_strength",
                            0,
                        )
                        or 0
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

    _log_timing(
        "semantic.validate_candidates",
        validation_started_at,
        candidates_in=len(consolidated_candidates),
        candidates_out=len(results),
    )

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
    Deterministically validate the structured part of a query.

    Structured requirements are validated from structured database records
    and remain independent from semantic evidence. This function also emits
    generic per-candidate diagnostics when a requirement fails so that a
    failing search can be diagnosed without adding query-specific rules.

    The diagnostics intentionally describe the actual requirement and the
    candidate data seen by the validator. No candidate name, skill, role, or
    query is hardcoded here.
    """
    candidate = db.get(
        Candidate,
        candidate_id,
    )

    if candidate is None:
        print(
            "[STRUCTURED VALIDATION] "
            f"candidate_id={candidate_id} FAIL reason=candidate_not_found",
            flush=True,
        )
        return False

    failures = []

    skills = requirements.get("skills") or []

    if skills:
        # Validate skills directly against CandidateSkill instead of the
        # selected semantic evidence. Semantic evidence is allowed to prove
        # semantic/activity requirements, but it must not silently substitute
        # for a structured skill requirement.
        candidate_skill_rows = db.execute(
            select(CandidateSkill.skill).where(
                CandidateSkill.candidate_id == candidate_id
            )
        ).scalars().all()

        candidate_skills = {
            _normalize_skill(skill)
            for skill in candidate_skill_rows
            if skill is not None
        }

        for skill in skills:
            normalized_skill = _normalize_skill(skill)

            if normalized_skill not in candidate_skills:
                evidence_text = "\n".join(
                    str(item.get("text") or "")
                    for item in evidence
                    if isinstance(item, dict)
                )

                normalized_evidence = _normalize_skill(
                    evidence_text
                )

                skill_tokens = normalized_skill.split()
                evidence_tokens = normalized_evidence.split()

                skill_found_in_evidence = bool(
                    skill_tokens
                    and len(skill_tokens) <= len(evidence_tokens)
                    and any(
                        evidence_tokens[index:index + len(skill_tokens)]
                        == skill_tokens
                        for index in range(
                            len(evidence_tokens) - len(skill_tokens) + 1
                        )
                    )
                )

                if not skill_found_in_evidence:
                    failures.append(
                        {
                            "type": "SKILL",
                            "required": skill,
                            "normalized_required": normalized_skill,
                            "available": sorted(candidate_skills),
                        }
                    )

    minimum_years = requirements.get(
        "experience_min_years"
    )

    if minimum_years is not None:
        required_months = float(
            minimum_years
        ) * 12

        actual_months = (
            candidate.total_experience_months
        )

        if (
            actual_months is None
            or float(actual_months) < required_months
        ):
            failures.append(
                {
                    "type": "EXPERIENCE",
                    "required_years": float(minimum_years),
                    "required_months": required_months,
                    "candidate_total_months": actual_months,
                }
            )

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

        experience_titles = [
            str(experience.title or "")
            for experience in experiences
        ]

        role_match = any(
            requested_role_tokens
            and all(
                token in title.lower()
                for token in requested_role_tokens
            )
            for title in experience_titles
        )

        if not role_match:
            failures.append(
                {
                    "type": "ROLE",
                    "required": str(role),
                    "experience_titles": experience_titles,
                }
            )

    if failures:
        print(
            "[STRUCTURED VALIDATION] "
            f"candidate_id={candidate_id} "
            f"name={candidate.name!r} FAIL "
            f"failures={failures}",
            flush=True,
        )
        return False

    print(
        "[STRUCTURED VALIDATION] "
        f"candidate_id={candidate_id} "
        f"name={candidate.name!r} PASS",
        flush=True,
    )

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

    The channels are UNIONED before final acceptance:
        1. structured retrieval discovers candidates matching structured
           constraints
        2. semantic retrieval discovers candidates matching semantic
           requirements
        3. structured-only candidates are also given semantic evidence
           retrieval so they can satisfy the semantic side of a hybrid
           query
        4. actual evidence is validated against every required condition
        5. only validated candidates are ranked
        6. requested_count is applied as a maximum

    A candidate does not have to be discovered by both retrieval channels
    to be eligible.
    """

    search_started_at = time.perf_counter()

    stage_started_at = time.perf_counter()

    structured_candidates = retrieve_structured_candidates(
        db,
        structured_requirements,
    )

    _log_timing(
        "unified.structured_retrieval",
        stage_started_at,
        rows=len(structured_candidates),
        candidates=len(
            {
                item["candidate"].id
                for item in structured_candidates
                if item.get("candidate") is not None
            }
        ),
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

    structured_candidate_ids = list(
        structured_map.keys()
    )

    semantic_requirements = [
        requirement
        for requirement in (requirements or [])
        if isinstance(requirement, dict)
        and (
            requirement.get("type")
            in {
                "ACTIVITY",
                "INDUSTRY",
                "OTHER",
            }
            or (
                requirement.get("type") == "EXPERIENCE"
                and requirement.get("scope") == "DOMAIN"
            )
        )
    ]

    # ---------------------------------------------------------
    # Pure structured search remains deterministic and cheap.
    # ---------------------------------------------------------
    if not semantic_requirements:
        prepared_candidates = (
            _prepare_structured_candidates_for_scoring(
                structured_candidates,
                structured_requirements,
            )
        )

        scored_candidates = score_candidates(
            prepared_candidates,
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

    semantic_text = _build_semantic_evaluation_query(
        semantic_requirements=semantic_requirements,
        fallback_query=(semantic_query or query),
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

    # ---------------------------------------------------------
    # SEMANTIC DISCOVERY CHANNEL
    #
    # This search is intentionally independent from structured
    # retrieval. It may discover candidates that have no matching
    # CandidateSkill row.
    # ---------------------------------------------------------
    stage_started_at = time.perf_counter()

    retrieval_requirements = _build_semantic_retrieval_requirements(
        semantic_requirements=semantic_requirements,
        structured_requirements=structured_requirements,
    )

    semantic_evidence = retrieve_semantic_candidates(
        query=semantic_text,
        limit=retrieval_limit,
        recency_months=recency_months,
        requirements=retrieval_requirements,
    )

    _log_timing(
        "unified.global_semantic_retrieval",
        stage_started_at,
        evidence=len(semantic_evidence),
        limit=retrieval_limit,
    )

    stage_started_at = time.perf_counter()

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
        structured_requirements=structured_requirements,
    )

    _log_timing(
        "unified.global_semantic_build",
        stage_started_at,
        results=len(semantic_results),
    )

    semantic_result_map = {
        result["id"]: result
        for result in semantic_results
    }

    # ---------------------------------------------------------
    # STRUCTURED CANDIDATES THAT WERE NOT DISCOVERED BY THE
    # GLOBAL SEMANTIC SEARCH MUST STILL GET A CHANCE.
    #
    # This is the important UNION behavior for hybrid search:
    # a valid structured candidate must not disappear merely
    # because it was outside the global semantic top-K.
    # ---------------------------------------------------------
    missing_structured_ids = [
        candidate_id
        for candidate_id in structured_candidate_ids
        if candidate_id not in semantic_result_map
    ]

    if missing_structured_ids:
        stage_started_at = time.perf_counter()

        targeted_semantic_evidence = (
            retrieve_semantic_candidates(
                query=semantic_text,
                limit=max(
                    requested_count * 20,
                    200,
                ),
                candidate_ids=missing_structured_ids,
                recency_months=recency_months,
                requirements=retrieval_requirements,
            )
        )

        _log_timing(
            "unified.targeted_semantic_retrieval",
            stage_started_at,
            candidate_ids=len(missing_structured_ids),
            evidence=len(targeted_semantic_evidence),
        )

        stage_started_at = time.perf_counter()

        targeted_semantic_results = _build_semantic_results(
            db=db,
            query=semantic_text,
            evidence=targeted_semantic_evidence,
            requested_count=max(
                requested_count,
                1,
            ),
            count_explicit=False,
            structured_map=None,
            semantic_requirements=semantic_requirements,
            structured_requirements=structured_requirements,
        )

        _log_timing(
            "unified.targeted_semantic_build",
            stage_started_at,
            results=len(targeted_semantic_results),
        )

        for result in targeted_semantic_results:
            candidate_id = result["id"]

            if candidate_id not in semantic_result_map:
                semantic_result_map[candidate_id] = result

    # ---------------------------------------------------------
    # UNION
    #
    # Every semantically validated candidate is eligible for the
    # final structured-constraint check, regardless of which
    # retrieval channel discovered it.
    # ---------------------------------------------------------
    candidate_ids = list(
        semantic_result_map.keys()
    )

    if not candidate_ids:
        return (
            [],
            (
                "HYBRID"
                if (
                    structured_requirements.get("skills")
                    or structured_requirements.get("role") is not None
                    or structured_requirements.get(
                        "experience_min_years"
                    ) is not None
                )
                else "SEMANTIC"
            ),
        )

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

    stage_started_at = time.perf_counter()

    for candidate_id, result in semantic_result_map.items():
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

    _log_timing(
        "unified.final_structured_validation",
        stage_started_at,
        candidates_in=len(semantic_result_map),
        candidates_out=len(final_results),
    )

    _log_timing(
        "unified.total",
        search_started_at,
        final_results=len(final_results),
    )

    # If the query contains both structured and semantic requirements,
    # report HYBRID. If it only contains semantic requirements, report
    # SEMANTIC.
    route = (
        "HYBRID"
        if (
            structured_requirements.get("skills")
            or structured_requirements.get("role") is not None
            or structured_requirements.get(
                "experience_min_years"
            ) is not None
        )
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

    # The requested count is a maximum, not a guarantee.
    # Never fill the remaining slots with candidates that failed
    # requirement validation.
    if count_explicit:
        final_results = final_results[
            :requested_count
        ]

    return (
        final_results,
        route,
    )
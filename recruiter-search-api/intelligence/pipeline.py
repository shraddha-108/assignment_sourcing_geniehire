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

from models import Candidate


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

    scored_candidates = score_candidates(
        candidates,
        requirements,
    )

    results = rank_candidates(
        scored_candidates,
        requested_count,
        count_explicit,
    )

    for result in results:
        result["match_status"] = "MATCH"

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
    )


def _build_semantic_results(
    db: Session,
    query: str,
    evidence: list[dict],
    requested_count: int,
    count_explicit: bool,
    structured_map: dict | None = None,
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

        best_reranker_score = float(
            item.get(
                "reranker_score",
                0,
            )
        )

        result = {
            "id": candidate.id,
            "name": candidate.name,
            "email": candidate.email,

            # IMPORTANT:
            # This remains MATCH for backward compatibility
            # with the current pipeline.
            #
            # Requirement-level validation will replace this
            # later with:
            #   MATCH
            #   PARTIAL_MATCH
            #
            # NO_MATCH candidates must be removed before the
            # final response.
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
    # STEP 5
    # Ranking remains based on the CrossEncoder relevance
    # signal.
    #
    # The signal is NOT exposed as a match percentage.
    # ---------------------------------------------------------

    results.sort(
        key=lambda item: item[
            "reranker_score"
        ],
        reverse=True,
    )

    if count_explicit:
        results = results[
            :requested_count
        ]

    return results
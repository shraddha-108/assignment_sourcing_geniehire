from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.retriever import (
    retrieve_structured_candidates,
    retrieve_semantic_candidates,
)
from intelligence.scorer import score_candidates
from intelligence.ranker import rank_candidates
from models import Candidate


def execute_structured_search(
    db: Session,
    requirements: dict,
    requested_count: int,
) -> list[dict]:

    candidates = retrieve_structured_candidates(
        db,
        requirements,
    )

    scored_candidates = score_candidates(
        candidates
    )

    return rank_candidates(
        scored_candidates,
        requested_count,
    )


def execute_semantic_search(
    db: Session,
    query: str,
    requested_count: int,
) -> list[dict]:

    evidence = retrieve_semantic_candidates(
        query=query,
        limit=max(requested_count * 10, 100),
    )

    if not evidence:
        return []

    candidate_ids = list(
        {
            item["candidate_id"]
            for item in evidence
            if item.get("candidate_id") is not None
        }
    )

    if not candidate_ids:
        return []

    candidates = db.scalars(
        select(Candidate).where(
            Candidate.id.in_(candidate_ids)
        )
    ).all()

    candidate_map = {
        candidate.id: candidate
        for candidate in candidates
    }

    best_matches = {}

    for item in evidence:
        candidate_id = item["candidate_id"]

        if candidate_id not in candidate_map:
            continue

        current = best_matches.get(candidate_id)

        if (
            current is None
            or item["similarity"] > current["similarity"]
        ):
            best_matches[candidate_id] = item

    results = []

    for candidate_id, evidence_item in best_matches.items():

        candidate = candidate_map[candidate_id]

        similarity = evidence_item["similarity"]

        results.append(
            {
                "id": candidate.id,
                "name": candidate.name,
                "email": candidate.email,
                "score": round(similarity * 100, 2),
                "evidence_type": evidence_item.get(
                    "chunk_type"
                ),
                "evidence": evidence_item.get(
                    "text"
                ),
                "similarity": round(
                    similarity,
                    4,
                ),
            }
        )

    results.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return results[:requested_count]
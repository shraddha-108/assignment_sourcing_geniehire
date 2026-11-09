from app.ingestion.vector.bm25 import bm25_query
from app.ingestion.vector.embeddings import embed_text
from app.ingestion.vector.qdrant_client import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    client,
    ensure_collection,
)
from qdrant_client.models import FieldCondition, Filter, MatchAny


def _candidate_filter(candidate_ids: list[int] | None):
    if not candidate_ids:
        return None
    return Filter(
        must=[
            FieldCondition(
                key="candidate_id",
                match=MatchAny(any=candidate_ids),
            )
        ]
    )


def dense_search(
    query: str,
    limit: int = 20,
    candidate_ids: list[int] | None = None,
):
    """
    Semantic search using dense embeddings.
    """

    if not query or not query.strip():
        return []

    ensure_collection()

    vector = embed_text(query)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        using=DENSE_VECTOR_NAME,
        query_filter=_candidate_filter(candidate_ids),
        limit=limit,
        with_payload=True,
    )

    return results.points


def bm25_search(
    query: str,
    limit: int = 20,
    candidate_ids: list[int] | None = None,
):
    """
    Lexical search using BM25 sparse vectors.
    """

    if not query or not query.strip():
        return []

    ensure_collection()

    vector = bm25_query(query)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        using=SPARSE_VECTOR_NAME,
        query_filter=_candidate_filter(candidate_ids),
        limit=limit,
        with_payload=True,
    )

    return results.points


def hybrid_search(
    query: str,
    limit: int = 20,
    candidate_ids: list[int] | None = None,
):
    """
    Perform both semantic and BM25 retrieval.

    Results are returned separately so the intelligence
    layer can perform candidate-level merging and scoring.
    """

    dense_results = dense_search(
        query=query,
        limit=limit,
        candidate_ids=candidate_ids,
    )

    bm25_results = bm25_search(
        query=query,
        limit=limit,
        candidate_ids=candidate_ids,
    )

    return {
        "dense": dense_results,
        "bm25": bm25_results,
    }

def retrieve_semantic_candidates(
    query: str,
    limit: int = 200,
    candidate_ids: list[int] | None = None,
    requirements: list[dict] | None = None,
) -> list[dict]:
    """Fuse dense and BM25 hits, returning evidence records for reranking."""

    if not query or not query.strip():
        return []

    if candidate_ids == []:
        return []

    searches = hybrid_search(
        query=query,
        limit=limit,
        candidate_ids=candidate_ids,
    )
    evidence_by_id: dict[str, dict] = {}
    allowed_candidate_ids = set(candidate_ids) if candidate_ids is not None else None

    for source, points in searches.items():
        for rank, point in enumerate(points, start=1):
            payload = point.payload or {}
            candidate_id = payload.get("candidate_id")

            if candidate_id is None:
                continue
            if (
                allowed_candidate_ids is not None
                and candidate_id not in allowed_candidate_ids
            ):
                continue

            evidence_id = str(
                payload.get("evidence_id", point.id)
            )
            reciprocal_rank_score = 1.0 / (60 + rank)

            if evidence_id not in evidence_by_id:
                evidence_by_id[evidence_id] = {
                    "candidate_id": candidate_id,
                    "evidence_id": payload.get("evidence_id"),
                    "resume_id": payload.get("resume_id"),
                    "resume_section_id": payload.get("resume_section_id"),
                    "evidence_type": payload.get("evidence_type"),
                    "text": payload.get("text", ""),
                    "retrieval_score": 0.0,
                    "retrieval_sources": [],
                }

            evidence = evidence_by_id[evidence_id]
            evidence["retrieval_score"] += reciprocal_rank_score
            evidence["retrieval_sources"].append(source)

    return sorted(
        evidence_by_id.values(),
        key=lambda item: item["retrieval_score"],
        reverse=True,
    )[:limit]

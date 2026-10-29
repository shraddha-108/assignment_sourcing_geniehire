from uuid import NAMESPACE_URL, uuid5

from qdrant_client.models import PointStruct

from app.ingestion.vector.bm25 import bm25_document
from app.ingestion.vector.embeddings import embed_text
from app.ingestion.vector.qdrant_client import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    client,
    ensure_collection,
)


def create_point_id(
    candidate_id: int,
    evidence_id: int,
) -> str:
    """
    Create a deterministic UUID for a candidate evidence record.

    The same candidate/evidence pair will always produce
    the same Qdrant point ID.
    """

    return str(
        uuid5(
            NAMESPACE_URL,
            f"candidate:{candidate_id}:evidence:{evidence_id}",
        )
    )


def index_evidence(
    *,
    candidate_id: int,
    evidence_id: int,
    resume_id: int,
    resume_section_id: int | None,
    evidence_type: str,
    text: str,
) -> str:
    """
    Convert one CandidateEvidence record into:

    - dense embedding
    - BM25 sparse vector

    and store both in Qdrant.
    """

    if not text or not text.strip():
        raise ValueError(
            "Evidence text cannot be empty."
        )

    ensure_collection()

    # --------------------------------------------------
    # Dense semantic vector
    # --------------------------------------------------

    dense_vector = embed_text(text)

    # --------------------------------------------------
    # Sparse BM25 vector
    # --------------------------------------------------

    sparse_vector = bm25_document(text)

    # --------------------------------------------------
    # Deterministic Qdrant point ID
    # --------------------------------------------------

    point_id = create_point_id(
        candidate_id,
        evidence_id,
    )

    # --------------------------------------------------
    # Payload
    # --------------------------------------------------

    payload = {
        "candidate_id": candidate_id,
        "evidence_id": evidence_id,
        "resume_id": resume_id,
        "resume_section_id": resume_section_id,
        "evidence_type": evidence_type,
        "text": text,
    }

    # --------------------------------------------------
    # Store both vectors
    # --------------------------------------------------

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=point_id,
                vector={
                    DENSE_VECTOR_NAME: dense_vector,
                    SPARSE_VECTOR_NAME: sparse_vector,
                },
                payload=payload,
            )
        ],
    )

    return point_id
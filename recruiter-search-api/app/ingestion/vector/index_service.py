from sqlalchemy import select
from sqlalchemy.orm import Session

from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.database.models.candidate_evidence import CandidateEvidence
from app.database.models.resume import Resume

from app.ingestion.vector.indexing import (
    index_evidence,
)
from app.ingestion.vector.qdrant_client import (
    COLLECTION_NAME,
    client,
    ensure_collection,
)


def index_candidate_evidence(
    db: Session,
    candidate_id: int,
) -> int:
    """
    Index all evidence belonging to one candidate.

    Returns the number of successfully indexed
    evidence records.
    """

    ensure_collection()

    evidence_records = db.scalars(
        select(CandidateEvidence)
        .where(
            CandidateEvidence.candidate_id
            == candidate_id
        )
    ).all()

    indexed_count = 0

    for evidence in evidence_records:

        resume = db.get(
            Resume,
            evidence.resume_id,
        )

        if resume is None:
            continue

        point_id = index_evidence(
            candidate_id=evidence.candidate_id,
            evidence_id=evidence.id,
            resume_id=resume.id,
            resume_section_id=evidence.resume_section_id,
            evidence_type=evidence.evidence_type,
            text=evidence.text,
        )

        evidence.qdrant_point_id = point_id

        indexed_count += 1

    db.commit()

    return indexed_count


def delete_candidate_evidence(
    candidate_id: int,
) -> None:
    """
    Delete all Qdrant evidence points belonging
    to a candidate.
    """

    ensure_collection()

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="candidate_id",
                    match=MatchValue(
                        value=candidate_id
                    ),
                )
            ]
        ),
    )
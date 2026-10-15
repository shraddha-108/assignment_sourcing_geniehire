from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Candidate, CandidateSkill
from ingestion.vectorDB.embedder import embed_text
from ingestion.vectorDB.qdrant_client import client, COLLECTION_NAME


def retrieve_structured_candidates(
    db: Session,
    requirements: dict,
) -> list[dict]:

    skills = requirements.get("skills", [])
    recency_months = requirements.get("recency_months")

    stmt = (
        select(Candidate, CandidateSkill)
        .join(
            CandidateSkill,
            Candidate.id == CandidateSkill.candidate_id,
        )
    )

    if skills:
        stmt = stmt.where(
            CandidateSkill.skill.in_(skills)
        )

    if recency_months is not None:
        cutoff_date = (
            date.today()
            - timedelta(days=recency_months * 30)
        )

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


def retrieve_semantic_candidates(
    query: str,
    limit: int = 100,
) -> list[dict]:

    query_vector = embed_text(query)

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    results = []

    for point in response.points:
        payload = point.payload or {}

        chunk_type = payload.get("chunk_type")

        if chunk_type == "education":
            continue

        candidate_id = payload.get("candidate_id")

        if candidate_id is None:
            continue

        results.append(
            {
                "candidate_id": candidate_id,
                "chunk_id": payload.get("chunk_id"),
                "chunk_type": chunk_type,
                "section": payload.get("section"),
                "text": payload.get("text"),
                "similarity": float(point.score),
            }
        )

    return results
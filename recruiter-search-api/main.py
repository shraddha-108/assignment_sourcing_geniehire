from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database import get_db
from models import Candidate, CandidateSkill

from ingestion.storage.s3_client import (
    BUCKET_NAME,
    s3_client,
)

from search.service import (
    build_routing_packet,
)

from intelligence.pipeline import (
    execute_unified_search,
)


app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str


@app.get("/health")
def health(
    db: Session = Depends(get_db),
):

    db.execute(
        text("SELECT 1")
    )

    return {
        "status": "ok",
    }


@app.get("/candidates/{candidate_id}/resume")
def get_candidate_resume(
    candidate_id: int,
    db: Session = Depends(get_db),
):

    candidate = db.get(
        Candidate,
        candidate_id,
    )

    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail="Candidate not found",
        )

    if not candidate.resume_storage_key:
        raise HTTPException(
            status_code=404,
            detail="Resume not found for this candidate",
        )

    resume_url = s3_client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": BUCKET_NAME,
            "Key": candidate.resume_storage_key,
            "ResponseContentType": "application/pdf",
            "ResponseContentDisposition": "inline",
        },
        ExpiresIn=300,
    )

    return {
        "candidate_id": candidate.id,
        "resume_url": resume_url,
    }


@app.post("/search")
def search(
    req: SearchRequest,
    db: Session = Depends(get_db),
):

    known_skills = list(
        db.scalars(
            select(
                CandidateSkill.skill
            ).distinct()
        ).all()
    )

    search_result = build_routing_packet(
        query=req.query,
        known_skills=known_skills,
    )

    if not search_result["valid"]:
        return search_result

    packet = search_result[
        "routing_packet"
    ]

    structured_requirements = packet[
        "structured_requirements"
    ]

    semantic_requirement = packet.get(
        "semantic_requirement"
    )

    requirements = packet.get(
        "requirements",
        [],
    )

    requested_count = packet[
        "requested_count"
    ]

    count_explicit = packet[
        "count_explicit"
    ]

    # The classifier still understands the query and
    # explains the intended route, but the route is no
    # longer used as a hard retrieval wall.
    #
    # Structured and semantic retrieval can independently
    # discover candidates. The pipeline then validates
    # the actual requirements before returning candidates.
    results, execution_route = execute_unified_search(
        db=db,
        query=packet["original_query"],
        structured_requirements=structured_requirements,
        semantic_query=semantic_requirement,
        requirements=requirements,
        requested_count=requested_count,
        count_explicit=count_explicit,
    )

    message = None

    if count_explicit:

        found_count = len(results)

        if found_count < requested_count:

            message = (
                f"Found {found_count} matching candidates. "
                f"You requested {requested_count}."
            )

    return {
        "route": execution_route,
        "parsed": packet,
        "results": results,
        "message": message,
    }
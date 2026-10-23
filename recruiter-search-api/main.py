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
    execute_structured_search,
    execute_semantic_search,
    execute_hybrid_search,
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

    route = search_result["route"]

    packet = search_result[
        "routing_packet"
    ]

    if route == "STRUCTURED":

        results = execute_structured_search(
            db=db,
            requirements=(
                packet[
                    "structured_requirements"
                ]
            ),
            requested_count=(
                packet[
                    "requested_count"
                ]
            ),
            count_explicit=(
                packet[
                    "count_explicit"
                ]
            ),
        )

        formatted_results = []

        for result in results:

            candidate = result[
                "candidate"
            ]

            formatted_results.append(
                {
                    "id": candidate.id,
                    "name": candidate.name,
                    "email": candidate.email,
                    "score": result[
                        "score"
                    ],
                    "matched_skills": [
                        {
                            "skill": result[
                                "skill"
                            ],
                            "last_used": (
                                result[
                                    "last_used_date"
                                ].isoformat()
                                if result[
                                    "last_used_date"
                                ]
                                else "unknown"
                            ),
                            "total_months": result[
                                "total_months"
                            ],
                        }
                    ],
                }
            )

        return {
            "route": route,
            "parsed": packet,
            "results": formatted_results,
        }

    if route == "SEMANTIC":

        results = execute_semantic_search(
            db=db,
            query=packet[
                "semantic_requirement"
            ],
            requirements=packet[
                "requirements"
            ],
            requested_count=packet[
                "requested_count"
            ],
            count_explicit=packet[
                "count_explicit"
            ],
        )

        return {
            "route": route,
            "parsed": packet,
            "results": results,
        }

    if route == "HYBRID":

        results = execute_hybrid_search(
            db=db,
            requirements=(
                packet[
                    "structured_requirements"
                ]
            ),
            semantic_query=packet[
                "semantic_requirement"
            ],
            semantic_requirements=packet[
                "requirements"
            ],
            requested_count=(
                packet[
                    "requested_count"
                ]
            ),
            count_explicit=(
                packet[
                    "count_explicit"
                ]
            ),
        )

        return {
            "route": route,
            "parsed": packet,
            "results": results,
        }

    return {
        "route": route,
        "parsed": packet,
        "results": [],
    }
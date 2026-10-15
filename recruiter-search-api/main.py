from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database import get_db
from models import CandidateSkill
from search.service import build_routing_packet
from intelligence.service import (
    execute_structured_search,
    execute_semantic_search,
)


app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str


@app.get("/health")
def health(
    db: Session = Depends(get_db),
):
    db.execute(text("SELECT 1"))

    return {
        "status": "ok"
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
            requirements=packet[
                "structured_requirements"
            ],
            requested_count=packet[
                "requested_count"
            ],
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
            requested_count=packet[
                "requested_count"
            ],
        )

        return {
            "route": route,
            "parsed": packet,
            "results": results,
        }

    if route == "HYBRID":

        return {
            "route": route,
            "parsed": packet,
            "results": [],
            "message": (
                "Hybrid retrieval not implemented yet."
            ),
        }

    return {
        "route": route,
        "parsed": packet,
        "results": [],
    }
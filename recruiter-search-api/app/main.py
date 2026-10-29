from pathlib import Path
import logging
import uuid
from time import perf_counter

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import get_db

from app.database.models.candidate import Candidate
from app.database.models.resume import Resume
from app.storage.s3_resume import generate_resume_presigned_url

from app.search.service import build_routing_packet
from app.search.spelling import suggest_query_correction

from app.intelligence.pipeline import execute_search


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app.search.api")


# ============================================================
# FastAPI application
# ============================================================

app = FastAPI(
    title="GenieHire Recruiter Search API",
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Request schemas
# ============================================================


class SearchRequest(BaseModel):
    query: str
    debug: bool = False


# ============================================================
# Health check
# ============================================================


@app.get("/")
def root():
    return {
        "service": "GenieHire Recruiter Search API",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
    }


# ============================================================
# Search endpoint
# ============================================================


@app.post("/search")
def search_candidates(
    request: SearchRequest,
    db: Session = Depends(get_db),
):
    """
    Main recruiter search endpoint.

    Flow:

        Recruiter query
              ↓
        Search Layer
              ↓
        RoutingPacket
              ↓
        Intelligence Layer
              ↓
        PostgreSQL + Qdrant
              ↓
        Validation
              ↓
        Scoring
              ↓
        Ranking
              ↓
        Frontend response
    """

    query = request.query.strip()

    if not query:
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty.",
        )

    search_id = str(uuid.uuid4())
    request_started = perf_counter()
    logger.info(
        "SEARCH REQUEST search_id=%s query_chars=%d",
        search_id,
        len(query),
    )

    try:

        # ----------------------------------------------------
        # 1. Search Layer
        # ----------------------------------------------------

        parsing_started = perf_counter()
        logger.info("SEARCH STAGE search_id=%s stage=query_parsing status=started", search_id)
        routing_packet = build_routing_packet(
            query
        )
        specification = routing_packet.specification
        logger.info(
            "SEARCH STAGE search_id=%s stage=query_parsing status=complete duration_s=%.3f route=%s requirements=%d assumptions=%d",
            search_id,
            perf_counter() - parsing_started,
            routing_packet.route,
            len(specification.requirements),
            len(specification.assumptions),
        )

        # ----------------------------------------------------
        # 2. Intelligence Layer
        # ----------------------------------------------------

        execution_trace = {"search_id": search_id, "debug": request.debug}
        results = execute_search(
            db=db,
            query=query,
            routing_packet=routing_packet,
            trace=execution_trace,
        )

        # ----------------------------------------------------
        # 3. Build frontend-compatible parsed object
        # ----------------------------------------------------
        #
        # Your frontend currently expects:
        #
        # parsed.original_query
        # parsed.requested_count
        # parsed.structured_requirements
        # parsed.semantic_requirement
        #
        # Our internal RoutingPacket uses:
        #
        # query
        # specification
        # semantic_requirements
        #
        # So we translate between backend architecture
        # and frontend response shape here.
        # ----------------------------------------------------

        specification = routing_packet.specification

        structured = (
            routing_packet.structured_requirements
        )

        semantic_requirements = (
            routing_packet.semantic_requirements
        )
        relevant_experience_months = [
            requirement.minimum_relevant_experience_months
            for requirement in specification.requirements
            if requirement.minimum_relevant_experience_months is not None
        ]
        temporal_windows = [
            requirement.temporal_window_months
            for requirement in specification.requirements
            if requirement.type.upper() == "TEMPORAL"
            and requirement.temporal_window_months is not None
        ]

        parsed_response = {
            "original_query": query,

            "requested_count": (
                specification.requested_count
            ),

            "count_explicit": specification.count_explicit,

            "structured_requirements": {
                "skills": (
                    structured.get("skills")
                    or []
                ),

                "roles": structured.get("roles") or [],
                "companies": structured.get("companies") or [],

                "location": structured.get("location"),

                "role": (
                    (
                        structured.get("roles")
                        or [None]
                    )[0]
                ),

                "recency_months": temporal_windows[0] if len(temporal_windows) == 1 else None,

                "experience_min_years": (
                    structured.get(
                        "min_experience_years"
                    )
                ),

                "experience_max_years": structured.get(
                    "max_experience_years"
                ),

                "relevant_experience_min_years": (
                    max(relevant_experience_months) / 12
                    if relevant_experience_months
                    else None
                ),
                "experience_scope": (
                    "RELEVANT" if relevant_experience_months else "OVERALL"
                ),
            },

            "semantic_requirement": (
                semantic_requirements[0]
                if semantic_requirements
                else None
            ),

            "semantic_requirements": semantic_requirements,

            "assumptions": specification.assumptions,

            "requirements": [
                item.model_dump(exclude_none=True)
                for item in specification.requirements
            ],

            "exclusions": [],
        }

        # ----------------------------------------------------
        # 4. Response
        # ----------------------------------------------------

        response = {
            "route": routing_packet.route,
            "suggested_query": suggest_query_correction(query),

            "search_specification": specification.model_dump(
                exclude_none=True
            ),

            "search_id": search_id,
            "execution_plan": execution_trace.get("execution_plan", {}),
            "execution_trace": execution_trace,

            "parsed": parsed_response,

            "results": results,

            "message": (
                f"Found {len(results)} matching "
                f"candidate"
                f"{'' if len(results) == 1 else 's'}."
            ),

            "valid": True,

            "errors": [],
        }
        logger.info(
            "SEARCH COMPLETE search_id=%s route=%s results=%d total_s=%.3f",
            search_id,
            routing_packet.route,
            len(results),
            perf_counter() - request_started,
        )
        return response

    except ValueError as exc:
        logger.warning(
            "SEARCH INVALID search_id=%s duration_s=%.3f error=%s",
            search_id,
            perf_counter() - request_started,
            exc,
        )

        return {
            "route": "STRUCTURED",
            "parsed": {
                "original_query": query,
                "requested_count": 10,
                "count_explicit": False,
                "structured_requirements": {
                    "skills": [],
                    "location": None,
                    "role": None,
                    "recency_months": None,
                    "experience_min_years": None,
                    "experience_scope": None,
                },
                "semantic_requirement": None,
                "exclusions": [],
            },
            "results": [],
            "message": None,
            "valid": False,
            "errors": [
                str(exc)
            ],
        }

    except Exception as exc:
        logger.exception(
            "SEARCH FAILED search_id=%s duration_s=%.3f error=%s",
            search_id,
            perf_counter() - request_started,
            exc,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "An error occurred while "
                "processing the search."
            ),
        )


# ============================================================
# View resume endpoint
# ============================================================


@app.get(
    "/candidates/{candidate_id}/resume"
)
def view_candidate_resume(
    candidate_id: int,
    db: Session = Depends(get_db),
):
    """
    Return the resume URL for a candidate.

    Frontend expects:

        {
            "candidate_id": 123,
            "resume_url": "..."
        }
    """

    resume_started = perf_counter()
    logger.info("RESUME REQUEST candidate_id=%d", candidate_id)

    # --------------------------------------------------------
    # Find candidate
    # --------------------------------------------------------

    candidate = db.scalar(
        select(Candidate).where(
            Candidate.id == candidate_id
        )
    )

    if candidate is None:
        logger.warning("RESUME NOT_FOUND candidate_id=%d reason=candidate", candidate_id)

        raise HTTPException(
            status_code=404,
            detail="Candidate not found.",
        )

    # --------------------------------------------------------
    # Find resume
    # --------------------------------------------------------

    resume = db.scalar(
        select(Resume)
        .where(
            Resume.candidate_id
            == candidate_id
        )
        .order_by(
            Resume.id.desc()
        )
    )

    if resume is None:
        logger.warning("RESUME NOT_FOUND candidate_id=%d reason=resume", candidate_id)

        raise HTTPException(
            status_code=404,
            detail=(
                "Resume not found for "
                "this candidate."
            ),
        )

    # --------------------------------------------------------
    # Resolve storage URL
    # --------------------------------------------------------

    storage_key = getattr(resume, "storage_key", None)

    if not storage_key:
        logger.warning("RESUME NOT_FOUND candidate_id=%d reason=storage_key", candidate_id)

        raise HTTPException(
            status_code=404,
            detail=(
                "Resume storage URL is not "
                "available."
            ),
        )

    # Generate a fresh short-lived URL for the existing private S3 object.
    # The URL is returned only; it is never persisted to the database.
    resume_url = generate_resume_presigned_url(storage_key)
    logger.info(
        "RESUME READY candidate_id=%d duration_s=%.3f",
        candidate_id,
        perf_counter() - resume_started,
    )

    # --------------------------------------------------------
    # Return frontend-compatible response
    # --------------------------------------------------------

    return {
        "candidate_id": candidate_id,
        "resume_url": resume_url,
    }

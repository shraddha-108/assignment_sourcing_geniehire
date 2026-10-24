from datetime import date, timedelta
import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from qdrant_client import models

from models import Candidate, CandidateSkill, Experience
from ingestion.vectorDB.embedder import embed_text
from ingestion.vectorDB.qdrant_client import (
    client,
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
)


SEMANTIC_RETRIEVAL_MIN_SCORE = float(
    os.getenv(
        "SEMANTIC_RETRIEVAL_MIN_SCORE",
        "0.10",
    )
)


def _parse_date(value):
    if value is None:
        return None

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        try:
            return date.fromisoformat(
                value[:10]
            )
        except ValueError:
            return None

    return None


def _cutoff_date(
    recency_months: int,
) -> date:

    return (
        date.today()
        - timedelta(
            days=recency_months * 30
        )
    )


def _experience_is_recent(
    start_date,
    end_date,
    cutoff_date: date,
) -> bool:

    parsed_start_date = _parse_date(
        start_date
    )

    parsed_end_date = _parse_date(
        end_date
    )

    if parsed_start_date is None:
        return False

    # A missing end date means the experience has
    # no known end date. We do not use it as proof
    # of recency unless the experience has started
    # within the requested recency window.
    if parsed_end_date is None:
        return (
            parsed_start_date <= date.today()
            and date.today() >= cutoff_date
        )

    return parsed_end_date >= cutoff_date


def _role_matches_title(
    role: str,
    title: str | None,
) -> bool:
    """
    Strict structured role matching.

    The structured layer only treats a role as satisfied when
    the meaningful words from the requested role are present
    in an actual Experience.title. This favors precision over
    semantic recall so unrelated roles do not pass merely
    because the candidate has related skills or industry evidence.

    Semantic role equivalence should be handled later by a
    dedicated semantic evaluator rather than guessed here.
    """

    if not role or not title:
        return False

    role_tokens = [
        token
        for token in role.lower().split()
        if token.strip()
    ]

    title_text = " ".join(
        title.lower().split()
    )

    return all(
        token in title_text
        for token in role_tokens
    )


def retrieve_structured_candidates(
    db: Session,
    requirements: dict,
) -> list[dict]:

    skills = requirements.get(
        "skills",
        [],
    )

    role = requirements.get(
        "role"
    )

    recency_months = requirements.get(
        "recency_months"
    )

    recency_scope = requirements.get(
        "recency_scope"
    )

    experience_min_years = requirements.get(
        "experience_min_years"
    )

    experience_scope = requirements.get(
        "experience_scope"
    )

    minimum_experience_months = None

    if experience_min_years is not None:
        minimum_experience_months = (
            experience_min_years * 12
        )

    stmt = (
        select(
            Candidate,
            CandidateSkill,
        )
        .join(
            CandidateSkill,
            Candidate.id
            == CandidateSkill.candidate_id,
        )
    )

    if role:
        role_candidates = db.execute(
            select(
                Experience.candidate_id
            )
            .where(
                Experience.title.is_not(None)
            )
            .distinct()
        ).scalars().all()

        matching_role_ids = []

        experiences_by_candidate = {}

        if role_candidates:
            role_experiences = (
                db.query(Experience)
                .filter(
                    Experience.candidate_id.in_(
                        role_candidates
                    )
                )
                .all()
            )

            for experience in role_experiences:
                experiences_by_candidate.setdefault(
                    experience.candidate_id,
                    [],
                ).append(experience)

        for candidate_id, experiences in (
            experiences_by_candidate.items()
        ):
            if any(
                _role_matches_title(
                    role,
                    experience.title,
                )
                for experience in experiences
            ):
                matching_role_ids.append(
                    candidate_id
                )

        if not matching_role_ids:
            return []

        stmt = stmt.where(
            Candidate.id.in_(
                matching_role_ids
            )
        )

    if skills:

        matching_candidates = (
            select(
                CandidateSkill.candidate_id
            )
            .where(
                CandidateSkill.skill.in_(
                    skills
                )
            )
            .group_by(
                CandidateSkill.candidate_id
            )
            .having(
                func.count(
                    func.distinct(
                        CandidateSkill.skill
                    )
                )
                == len(skills)
            )
            .subquery()
        )

        stmt = stmt.where(
            Candidate.id.in_(
                select(
                    matching_candidates.c.candidate_id
                )
            )
        )

        stmt = stmt.where(
            CandidateSkill.skill.in_(
                skills
            )
        )

        if (
            minimum_experience_months
            is not None
        ):

            if (
                experience_scope
                == "SKILL"
            ):

                stmt = stmt.where(
                    CandidateSkill.total_months
                    >= minimum_experience_months
                )

            else:

                stmt = stmt.where(
                    Candidate.total_experience_months
                    >= minimum_experience_months
                )

    elif (
        minimum_experience_months
        is not None
    ):

        stmt = stmt.where(
            Candidate.total_experience_months
            >= minimum_experience_months
        )

    # Structured recency applies only when the
    # recruiter is asking for recent use of the
    # structured skill.
    #
    # Example:
    # "recent Python developers"
    #
    # Semantic recency must never be converted
    # into recent use of the structured skill.
    if (
        recency_months is not None
        and (
            recency_scope is None
            or recency_scope == "SKILL"
        )
        and skills
    ):

        cutoff_date = _cutoff_date(
            recency_months
        )

        stmt = stmt.where(
            CandidateSkill.last_used_date
            >= cutoff_date
        )

    rows = db.execute(stmt).all()

    results = []

    for candidate, skill in rows:

        results.append(
            {
                "candidate": candidate,
                "skill": skill.skill,
                "last_used_date": (
                    skill.last_used_date
                ),
                "total_months": (
                    skill.total_months
                ),
            }
        )

    return results


def retrieve_semantic_candidates(
    query: str,
    limit: int = 100,
    candidate_ids: list[int] | None = None,
    recency_months: int | None = None,
    requirements: list[dict] | None = None,
    min_retrieval_score: float | None = None,
) -> list[dict]:

    dense_query = embed_text(query)

    filter_conditions = []

    # Hybrid search restricts semantic retrieval
    # to candidates who already satisfied the
    # structured requirements.
    if candidate_ids:

        filter_conditions.append(
            models.FieldCondition(
                key="candidate_id",
                match=models.MatchAny(
                    any=candidate_ids
                ),
            )
        )

    # IMPORTANT:
    # Do not turn semantic recency into an Experience-only
    # retrieval filter.
    #
    # Retrieval should find evidence relevant to the semantic
    # requirement first. Validation is responsible for deciding
    # whether that evidence actually proves the requested
    # recency.
    #
    # Example:
    # "recently built machine learning projects"
    #
    # A Project chunk may be the strongest evidence that the
    # candidate built an ML project, even though the current
    # Project chunk model has no date.
    #
    # We must NOT reject that evidence during retrieval, and we
    # must NOT borrow an unrelated Experience date and treat it
    # as the project's date.
    #
    # The validation layer should distinguish:
    #   1. requirement supported + recent
    #   2. requirement supported + not recent
    #   3. requirement supported but recency cannot be established
    #
    # requirements is carried forward with each result so the
    # downstream validation layer knows which semantic claim is
    # being evaluated.
    semantic_requirements = requirements or []

    query_filter = None

    if filter_conditions:

        query_filter = models.Filter(
            must=filter_conditions
        )

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=[
            models.Prefetch(
                query=dense_query,
                using=DENSE_VECTOR_NAME,
                limit=limit,
                filter=query_filter,
            ),
            models.Prefetch(
                query=models.Document(
                    text=query,
                    model="Qdrant/bm25",
                ),
                using=SPARSE_VECTOR_NAME,
                limit=limit,
                filter=query_filter,
            ),
        ],
        query=models.FusionQuery(
            fusion=models.Fusion.RRF
        ),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    # Kept for backward compatibility with callers that still
    # provide recency_months. The value is intentionally not
    # used as a blanket Experience-only filter here.
    #
    # Temporal validation belongs to the requirement-level
    # validation stage because the current vector chunks do not
    # have dates for every evidence type.
    cutoff_date = None

    if recency_months is not None:
        cutoff_date = _cutoff_date(
            recency_months
        )

    results = []

    retrieval_score_threshold = (
        SEMANTIC_RETRIEVAL_MIN_SCORE
        if min_retrieval_score is None
        else min_retrieval_score
    )

    seen = set()

    for point in response.points:

        payload = point.payload or {}

        chunk_type = payload.get(
            "chunk_type"
        )

        if chunk_type == "education":
            continue

        candidate_id = payload.get(
            "candidate_id"
        )

        chunk_id = payload.get(
            "chunk_id"
        )

        text = payload.get(
            "text",
            "",
        )

        if candidate_id is None:
            continue

        if not text:
            continue

        retrieval_score = float(point.score)

        # This is only an initial retrieval-quality gate.
        # It is intentionally not treated as a qualification score.
        if retrieval_score < retrieval_score_threshold:
            continue

        # Do not perform requirement validation here.
        #
        # In particular:
        # - an undated Project chunk may still be valid semantic
        #   evidence for the activity itself;
        # - an Experience date must not automatically become the
        #   date of a separate project/activity;
        # - recency must be proven using evidence that legitimately
        #   belongs to the requirement being evaluated.
        #
        # The downstream validation layer receives the requirement,
        # evidence, and any dates attached to that evidence and
        # decides whether the requirement is MATCH, PARTIAL_MATCH,
        # or NO_MATCH.

        evidence_key = (
            candidate_id,
            chunk_id,
            text,
        )

        if evidence_key in seen:
            continue

        seen.add(evidence_key)

        results.append(
            {
                "candidate_id": candidate_id,
                "chunk_id": chunk_id,
                "chunk_type": chunk_type,
                "section": payload.get(
                    "section"
                ),
                "text": text,

                "company": payload.get(
                    "company"
                ),
                "job_title": payload.get(
                    "job_title"
                ),
                "start_date": payload.get(
                    "start_date"
                ),
                "end_date": payload.get(
                    "end_date"
                ),
                "project_title": payload.get(
                    "project_title"
                ),

                # Requirement context is metadata only.
                # It is not a match decision.
                "requirements": semantic_requirements,

                # RRF retrieval score.
                # This is an internal retrieval
                # signal, not a match percentage.
                "retrieval_score": retrieval_score,
            }
        )

    return results


def consolidate_candidate_evidence(
    evidence: list[dict],
    max_chunks_per_candidate: int = 3,
) -> list[dict]:

    grouped: dict[
        int,
        list[dict],
    ] = {}

    for item in evidence:

        candidate_id = item.get(
            "candidate_id"
        )

        if candidate_id is None:
            continue

        grouped.setdefault(
            candidate_id,
            [],
        ).append(item)

    candidates = []

    for candidate_id, chunks in grouped.items():

        chunks.sort(
            key=lambda item: item.get(
                "reranker_score",
                item.get(
                    "retrieval_score",
                    0,
                ),
            ),
            reverse=True,
        )

        selected = []
        seen_text = set()

        for chunk in chunks:

            normalized_text = " ".join(
                chunk.get(
                    "text",
                    "",
                )
                .lower()
                .split()
            )

            if not normalized_text:
                continue

            if normalized_text in seen_text:
                continue

            seen_text.add(
                normalized_text
            )

            selected.append(chunk)

            if (
                len(selected)
                >= max_chunks_per_candidate
            ):
                break

        if not selected:
            continue

        reranker_scores = [
            float(
                item.get(
                    "reranker_score",
                    0,
                )
            )
            for item in selected
        ]

        best_reranker_score = max(
            reranker_scores
        )

        candidates.append(
            {
                "candidate_id": candidate_id,
                "evidence": selected,
                "reranker_score": (
                    best_reranker_score
                ),
            }
        )

    candidates.sort(
        key=lambda candidate: candidate[
            "reranker_score"
        ],
        reverse=True,
    )

    return candidates
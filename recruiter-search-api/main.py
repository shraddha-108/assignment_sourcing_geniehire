from datetime import date, timedelta

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database import get_db
from models import Candidate, CandidateSkill
from search_parser import parse_query

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str


def skill_score(last_used: date | None, total_months: int) -> float:
    """0-100. 60% recency (full marks today, zero after 5 years), 40% experience (caps at 5 years)."""
    if last_used is None:
        recency = 0.0
    else:
        months_ago = (date.today() - last_used).days / 30
        recency = max(0.0, 1 - months_ago / 60)
    experience = min(total_months, 60) / 60
    return 100 * (0.6 * recency + 0.4 * experience)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/search")
def search(req: SearchRequest, db: Session = Depends(get_db)):
    known_skills = list(db.scalars(select(CandidateSkill.skill).distinct()).all())
    parsed = parse_query(req.query, known_skills)

    if not parsed["skills"]:
        return {
            "parsed": parsed,
            "results": [],
            "message": "I couldn't find a known skill in your query. "
                       f"Try one of: {', '.join(sorted(known_skills))}",
        }

    stmt = (
        select(Candidate, CandidateSkill)
        .join(CandidateSkill, CandidateSkill.candidate_id == Candidate.id)
        .where(CandidateSkill.skill.in_(parsed["skills"]))
    )
    if parsed["recency_months"]:
        cutoff = date.today() - timedelta(days=30 * parsed["recency_months"])
        stmt = stmt.where(CandidateSkill.last_used_date >= cutoff)

    # Group matching skill rows by candidate
    grouped: dict[int, dict] = {}
    for candidate, cs in db.execute(stmt).all():
        entry = grouped.setdefault(candidate.id, {"candidate": candidate, "skills": []})
        entry["skills"].append(cs)

    results = []
    for entry in grouped.values():
        # candidate must match ALL requested skills
        if len(entry["skills"]) < len(parsed["skills"]):
            continue
        scores = [skill_score(s.last_used_date, s.total_months) for s in entry["skills"]]
        c = entry["candidate"]
        results.append({
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "score": round(sum(scores) / len(scores)),
            "matched_skills": [
                {
                    "skill": s.skill,
                    "last_used": s.last_used_date.isoformat() if s.last_used_date else "unknown",
                    "total_months": s.total_months,
                }
                for s in entry["skills"]
            ],
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return {"parsed": parsed, "results": results[: parsed["limit"]]}
from sqlalchemy.orm import Session

from models import Candidate, CandidateSkill, Experience


def candidate_exists(
    db: Session,
    resume_hash: str,
) -> bool:
    return (
        db.query(Candidate)
        .filter(
            Candidate.resume_hash == resume_hash
        )
        .first()
        is not None
    )


def create_candidate(
    db: Session,
    candidate_data: dict,
    resume_filename: str,
    resume_hash: str,
) -> Candidate:

    candidate = Candidate(
        name=candidate_data["name"],
        email=candidate_data.get("email"),
        phone=candidate_data.get("phone"),
        resume_filename=resume_filename,
        resume_hash=resume_hash,
        total_experience_months=candidate_data.get(
            "total_experience_months",
            0,
        ),
    )

    for experience in candidate_data.get(
        "experiences",
        [],
    ):
        candidate.experiences.append(
            Experience(
                company=experience.get("company"),
                title=experience.get("title"),
                start_date=experience.get("start_date"),
                end_date=experience.get("end_date"),
                duration_months=experience.get(
                    "duration_months",
                    0,
                ),
            )
        )

    for skill in candidate_data.get(
        "skills",
        [],
    ):
        candidate.skills.append(
            CandidateSkill(
                skill=skill["skill"],
                last_used_date=skill.get(
                    "last_used_date"
                ),
                total_months=skill.get(
                    "total_months",
                    0,
                ),
            )
        )

    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    return candidate
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    candidate_id: Mapped[int] = mapped_column(
        ForeignKey(
            "candidates.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id"),
        nullable=False,
        index=True,
    )

    years_of_experience: Mapped[float | None] = mapped_column(
        Float
    )

    months_of_experience: Mapped[int | None] = mapped_column(
        Integer
    )

    first_used_date: Mapped[date | None] = mapped_column(
        Date
    )

    last_used_date: Mapped[date | None] = mapped_column(
        Date
    )

    proficiency: Mapped[str | None] = mapped_column(
        String(50)
    )

    confidence: Mapped[float | None] = mapped_column(
        Float
    )

    evidence: Mapped[str | None] = mapped_column(
        Text
    )

    candidate: Mapped["Candidate"] = relationship(
        back_populates="candidate_skills"
    )

    skill: Mapped["Skill"] = relationship(
        back_populates="candidate_skills"
    )
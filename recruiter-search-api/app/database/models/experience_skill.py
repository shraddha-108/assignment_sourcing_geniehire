from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ExperienceSkill(Base):
    __tablename__ = "experience_skills"

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

    experience_id: Mapped[int] = mapped_column(
        ForeignKey(
            "experiences.id",
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

    first_used_date: Mapped[date | None] = mapped_column(
        Date
    )

    last_used_date: Mapped[date | None] = mapped_column(
        Date
    )

    months_used: Mapped[int | None] = mapped_column(
        Integer
    )

    confidence: Mapped[float | None] = mapped_column(
        Float
    )

    evidence: Mapped[str | None] = mapped_column(
        Text
    )

    candidate: Mapped["Candidate"] = relationship(
        back_populates="experience_skills"
    )

    experience: Mapped["Experience"] = relationship(
        back_populates="skills"
    )

    skill: Mapped["Skill"] = relationship(
        back_populates="experience_skills"
    )
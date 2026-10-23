from datetime import date, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(200)
    )

    email: Mapped[str | None] = mapped_column(
        String(200)
    )

    phone: Mapped[str | None] = mapped_column(
        String(50)
    )

    resume_filename: Mapped[str] = mapped_column(
        String(500)
    )

    resume_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )

    resume_storage_key: Mapped[str | None] = (
        mapped_column(
            String(1000)
        )
    )

    total_experience_months: Mapped[int] = (
        mapped_column(
            default=0
        )
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    experiences: Mapped[list["Experience"]] = (
        relationship(
            back_populates="candidate",
            cascade="all, delete-orphan",
        )
    )

    skills: Mapped[list["CandidateSkill"]] = (
        relationship(
            back_populates="candidate",
            cascade="all, delete-orphan",
        )
    )


class Experience(Base):
    __tablename__ = "experiences"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    candidate_id: Mapped[int] = mapped_column(
        ForeignKey(
            "candidates.id",
            ondelete="CASCADE",
        )
    )

    company: Mapped[str | None] = mapped_column(
        String(200)
    )

    title: Mapped[str | None] = mapped_column(
        String(200)
    )

    start_date: Mapped[date | None]

    end_date: Mapped[date | None]

    duration_months: Mapped[int] = mapped_column(
        default=0
    )

    candidate: Mapped[Candidate] = relationship(
        back_populates="experiences"
    )


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    candidate_id: Mapped[int] = mapped_column(
        ForeignKey(
            "candidates.id",
            ondelete="CASCADE",
        )
    )

    skill: Mapped[str] = mapped_column(
        String(100)
    )

    last_used_date: Mapped[date | None]

    total_months: Mapped[int] = mapped_column(
        default=0
    )

    candidate: Mapped[Candidate] = relationship(
        back_populates="skills"
    )

    __table_args__ = (
        Index(
            "idx_skill_recency",
            "skill",
            "last_used_date",
        ),
        UniqueConstraint(
            "candidate_id",
            "skill",
            name="uq_candidate_skill",
        ),
    )
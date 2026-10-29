from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    email: Mapped[str | None] = mapped_column(
        String(200),
    )

    phone: Mapped[str | None] = mapped_column(
        String(50),
    )

    headline: Mapped[str | None] = mapped_column(
        String(300),
    )

    summary: Mapped[str | None] = mapped_column(
        Text,
    )

    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"),
    )

    location: Mapped["Location | None"] = relationship(
        back_populates="candidates",
    )

    current_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"),
    )

    current_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id"),
    )

    current_company: Mapped["Company | None"] = relationship(
        foreign_keys=[current_company_id],
    )

    current_role: Mapped["Role | None"] = relationship(
        foreign_keys=[current_role_id],
    )

    total_experience_months: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    linkedin_url: Mapped[str | None] = mapped_column(
        String(500),
    )

    github_url: Mapped[str | None] = mapped_column(
        String(500),
    )

    portfolio_url: Mapped[str | None] = mapped_column(
        String(500),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    experiences: Mapped[list["Experience"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )

    candidate_skills: Mapped[list["CandidateSkill"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )

    experience_skills: Mapped[list["ExperienceSkill"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )

    projects: Mapped[list["Project"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )

    education: Mapped[list["Education"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )

    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )

    evidence: Mapped[list["CandidateEvidence"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
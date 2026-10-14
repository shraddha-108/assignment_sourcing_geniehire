from datetime import date
from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))

    experiences: Mapped[list["Experience"]] = relationship(back_populates="candidate")
    skills: Mapped[list["CandidateSkill"]] = relationship(back_populates="candidate")


class Experience(Base):
    __tablename__ = "experiences"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    company: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]  # None = current job

    candidate: Mapped[Candidate] = relationship(back_populates="experiences")


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    skill: Mapped[str] = mapped_column(String(100))  # normalized, e.g. "python"
    last_used_date: Mapped[date | None]               # the recency field
    total_months: Mapped[int] = mapped_column(default=0)

    candidate: Mapped[Candidate] = relationship(back_populates="skills")

    __table_args__ = (Index("idx_skill_recency", "skill", "last_used_date"),)
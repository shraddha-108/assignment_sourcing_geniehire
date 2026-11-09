from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    normalized_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        unique=True,
        index=True,
    )

    skill_type: Mapped[str | None] = mapped_column(
        String(100),
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text
    )

    candidate_skills: Mapped[list["CandidateSkill"]] = relationship(
        back_populates="skill"
    )

    experience_skills: Mapped[list["ExperienceSkill"]] = relationship(
        back_populates="skill"
    )

    project_skills: Mapped[list["ProjectSkill"]] = relationship(
        back_populates="skill"
    )

    domain_memberships: Mapped[list["TechnologyDomainMember"]] = relationship(
        back_populates="skill"
    )
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ProjectSkill(Base):
    __tablename__ = "project_skills"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey(
            "projects.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    skill_id: Mapped[int] = mapped_column(
        ForeignKey(
            "skills.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(
        back_populates="skills"
    )

    skill: Mapped["Skill"] = relationship(
        back_populates="project_skills"
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "skill_id",
            name="uq_project_skill",
        ),
    )
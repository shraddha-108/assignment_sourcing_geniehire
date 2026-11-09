from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Project(Base):
    __tablename__ = "projects"

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

    title: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text
    )

    url: Mapped[str | None] = mapped_column(
        String(500)
    )

    candidate: Mapped["Candidate"] = relationship(
        back_populates="projects"
    )

    skills: Mapped[list["ProjectSkill"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
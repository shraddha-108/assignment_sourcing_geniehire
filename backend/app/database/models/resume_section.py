from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ResumeSection(Base):
    __tablename__ = "resume_sections"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    resume_id: Mapped[int] = mapped_column(
        ForeignKey(
            "resumes.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    section_type: Mapped[str] = mapped_column(
        nullable=False,
        index=True,
    )

    title: Mapped[str | None] = mapped_column()

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    section_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    resume: Mapped["Resume"] = relationship(
        back_populates="sections"
    )
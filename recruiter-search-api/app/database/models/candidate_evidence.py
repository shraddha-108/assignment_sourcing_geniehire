from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class CandidateEvidence(Base):
    __tablename__ = "candidate_evidence"

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

    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "resumes.id",
            ondelete="SET NULL",
        ),
        index=True,
    )

    resume_section_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "resume_sections.id",
            ondelete="SET NULL",
        ),
        index=True,
    )

    evidence_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    qdrant_point_id: Mapped[str | None] = mapped_column(
        String(200),
        index=True,
    )

    candidate: Mapped["Candidate"] = relationship(
        back_populates="evidence"
    )
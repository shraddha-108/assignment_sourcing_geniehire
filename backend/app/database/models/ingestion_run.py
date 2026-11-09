from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    resume_id: Mapped[int] = mapped_column(
        ForeignKey(
            "resumes.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="PENDING",
        index=True,
    )

    current_stage: Mapped[str | None] = mapped_column(
        String(100),
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    resume: Mapped["Resume"] = relationship(
        back_populates="ingestion_runs",
    )
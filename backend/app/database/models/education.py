from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Education(Base):
    __tablename__ = "education"

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

    institution: Mapped[str | None] = mapped_column(
        String(300)
    )

    degree: Mapped[str | None] = mapped_column(
        String(200)
    )

    field_of_study: Mapped[str | None] = mapped_column(
        String(200)
    )

    start_date: Mapped[date | None] = mapped_column(
        Date
    )

    end_date: Mapped[date | None] = mapped_column(
        Date
    )

    description: Mapped[str | None] = mapped_column(
        Text
    )

    candidate: Mapped["Candidate"] = relationship(
        back_populates="education"
    )
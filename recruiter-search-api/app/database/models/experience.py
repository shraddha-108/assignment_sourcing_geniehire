from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Experience(Base):
    __tablename__ = "experiences"

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

    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"),
        index=True,
    )

    role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id"),
        index=True,
    )

    start_date: Mapped[date | None] = mapped_column(
        Date
    )

    end_date: Mapped[date | None] = mapped_column(
        Date
    )

    is_current: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    duration_months: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text
    )

    candidate: Mapped["Candidate"] = relationship(
        back_populates="experiences"
    )

    company: Mapped["Company | None"] = relationship(
        back_populates="experiences"
    )

    role: Mapped["Role | None"] = relationship(
        back_populates="experiences"
    )

    skills: Mapped[list["ExperienceSkill"]] = relationship(
        back_populates="experience",
        cascade="all, delete-orphan",
    )
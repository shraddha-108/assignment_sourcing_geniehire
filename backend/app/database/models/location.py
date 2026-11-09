from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    state: Mapped[str | None] = mapped_column(
        String(100),
        index=True,
    )

    country: Mapped[str | None] = mapped_column(
        String(100),
        index=True,
    )

    normalized_city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    normalized_state: Mapped[str | None] = mapped_column(
        String(100),
        index=True,
    )

    normalized_country: Mapped[str | None] = mapped_column(
        String(100),
        index=True,
    )

    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="location"
    )
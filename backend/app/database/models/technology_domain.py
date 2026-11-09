from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class TechnologyDomain(Base):
    __tablename__ = "technology_domains"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        unique=True,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text
    )

    members: Mapped[list["TechnologyDomainMember"]] = relationship(
        back_populates="domain",
        cascade="all, delete-orphan",
    )
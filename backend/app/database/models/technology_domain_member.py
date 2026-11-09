from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class TechnologyDomainMember(Base):
    __tablename__ = "technology_domain_members"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    domain_id: Mapped[int] = mapped_column(
        ForeignKey(
            "technology_domains.id",
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

    domain: Mapped["TechnologyDomain"] = relationship(
        back_populates="members"
    )

    skill: Mapped["Skill"] = relationship(
        back_populates="domain_memberships"
    )

    __table_args__ = (
        UniqueConstraint(
            "domain_id",
            "skill_id",
            name="uq_domain_skill",
        ),
    )
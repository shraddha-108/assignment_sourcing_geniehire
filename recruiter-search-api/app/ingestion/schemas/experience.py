
from datetime import date

from pydantic import BaseModel, Field


class ExperienceData(BaseModel):
    company: str | None = None
    title: str | None = None

    start_date: date | None = None
    end_date: date | None = None

    duration_months: int = 0

    skills: list[str] = Field(
        default_factory=list
    )

    evidence: str = ""

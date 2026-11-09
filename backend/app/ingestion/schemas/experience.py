
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


EmploymentType = Literal[
    "FULL_TIME",
    "PART_TIME",
    "INTERNSHIP",
    "CONTRACT",
    "FREELANCE",
    "APPRENTICESHIP",
]

SeniorityLevel = Literal[
    "JUNIOR",
    "MID_LEVEL",
    "SENIOR",
    "LEAD",
    "PRINCIPAL",
    "MANAGER",
    "DIRECTOR",
]


class ExperienceData(BaseModel):
    company: str | None = None
    title: str | None = None

    start_date: date | None = None
    end_date: date | None = None

    duration_months: int = 0

    # Employment classification
    employment_type: EmploymentType | None = Field(
        default=None,
        description=(
            "Employment type explicitly supported by the resume. "
            "Return null when unclear."
        ),
    )

    # Job seniority
    seniority_level: SeniorityLevel | None = Field(
        default=None,
        description=(
            "Job seniority based on title and responsibilities. "
            "Do not determine seniority from years alone. "
            "Return null when evidence is insufficient."
        ),
    )

    skills: list[str] = Field(
        default_factory=list
    )

    evidence: str = ""

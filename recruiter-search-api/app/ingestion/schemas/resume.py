from pydantic import BaseModel, Field

from app.ingestion.schemas.candidate import CandidateData
from app.ingestion.schemas.education import EducationData
from app.ingestion.schemas.experience import ExperienceData
from app.ingestion.schemas.project import ProjectData
from app.ingestion.schemas.skill import SkillData


class ResumeData(BaseModel):
    candidate: CandidateData

    experiences: list[ExperienceData] = Field(
        default_factory=list
    )

    skills: list[SkillData] = Field(
        default_factory=list
    )

    projects: list[ProjectData] = Field(
        default_factory=list
    )

    education: list[EducationData] = Field(
        default_factory=list
    )

    total_experience_months: int = 0

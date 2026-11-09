from pydantic import BaseModel, Field


class ProjectData(BaseModel):
    title: str = ""

    description: str = ""

    skills: list[str] = Field(
        default_factory=list
    )

    evidence: str = ""
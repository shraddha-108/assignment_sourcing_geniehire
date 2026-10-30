from pydantic import BaseModel


class SkillData(BaseModel):
    name: str
    skill_type: str | None = None
    description: str | None = None
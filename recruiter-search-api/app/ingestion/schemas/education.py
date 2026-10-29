from datetime import date

from pydantic import BaseModel


class EducationData(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None

    start_date: date | None = None
    end_date: date | None = None
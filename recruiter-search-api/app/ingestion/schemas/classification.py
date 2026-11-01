from enum import Enum

from pydantic import BaseModel, Field


class ResumeDomain(str, Enum):
    TECHNICAL = "TECHNICAL"
    SALES = "SALES"
    MARKETING = "MARKETING"
    HR = "HR"
    FINANCE = "FINANCE"
    OPERATIONS = "OPERATIONS"
    CUSTOMER_SUCCESS = "CUSTOMER_SUCCESS"
    PRODUCT = "PRODUCT"
    GENERAL = "GENERAL"


class ResumeClassification(BaseModel):
    primary_domain: ResumeDomain = Field(
        description="The candidate's primary professional domain."
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Model-estimated confidence between 0 and 1."
    )
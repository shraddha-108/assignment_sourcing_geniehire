from pydantic import BaseModel


class CandidateData(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None

    headline: str | None = None
    summary: str | None = None
    location: str | None = None

    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None

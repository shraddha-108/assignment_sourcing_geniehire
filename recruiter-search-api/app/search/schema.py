from typing import Literal
from typing import Any

from pydantic import BaseModel, Field


SearchRoute = Literal["STRUCTURED", "SEMANTIC", "HYBRID"]
RequirementType = str
RequirementRelationship = str


class SearchRequirement(BaseModel):
    """One recruiter requirement and the capabilities needed to resolve it."""

    id: str
    original_text: str
    normalized_text: str
    type: RequirementType
    mandatory: bool = True
    match_mode: Literal["HARD", "SOFT"] | None = None
    source_of_truth: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    related_requirements: list[str] = Field(default_factory=list)
    group_id: str | None = None
    relationship: RequirementRelationship = "AND"
    confidence: float | None = Field(default=None, ge=0, le=1)
    field: str | None = None
    value: str | int | float | bool | list[str] | dict[str, Any] | None = None
    canonical_value: str | None = None
    equivalent_terms: list[str] = Field(default_factory=list)
    semantic_expansions: list[str] = Field(default_factory=list)
    min_experience_exclusive: bool = False
    temporal_window_months: int | None = Field(default=None, ge=0)
    minimum_relevant_experience_months: int | None = Field(default=None, ge=0)


class SearchSpecification(BaseModel):
    """
    Canonical representation of a recruiter search query.

    This object is the contract between query understanding
    and the rest of the search system.
    """

    requested_count: int = Field(
        default=10,
        ge=1,
        description="Number of candidates requested by the recruiter.",
    )

    count_explicit: bool = Field(
        default=False,
        description="Whether the recruiter explicitly requested a result count.",
    )

    skills: list[str] = Field(
        default_factory=list,
        description="Explicit technical skills required.",
    )

    roles: list[str] = Field(
        default_factory=list,
        description="Roles or job titles requested.",
    )

    companies: list[str] = Field(
        default_factory=list,
        description="Companies explicitly mentioned in the query.",
    )

    location: str | None = Field(
        default=None,
        description="Candidate city or location requested by the recruiter.",
    )

    min_experience_years: float | None = Field(
        default=None,
        ge=0,
        description="Minimum total experience in years.",
    )

    max_experience_years: float | None = Field(
        default=None,
        ge=0,
        description="Maximum total experience in years.",
    )

    semantic_requirements: list[str] = Field(
        default_factory=list,
        description=(
            "Requirements that depend on meaning or resume evidence, "
            "such as projects, responsibilities, products, or achievements."
        ),
    )

    assumptions: list[str] = Field(
        default_factory=list,
        description="Explicitly disclosed defaults inferred from recruiter wording.",
    )

    requirements: list[SearchRequirement] = Field(
        default_factory=list,
        description="Extensible requirement graph extracted from the query.",
    )

    route: SearchRoute = Field(
        default="STRUCTURED",
        description="Search route selected after classification.",
    )


class ParsedQuery(BaseModel):
    """
    LLM output before routing.

    The LLM extracts what the recruiter wants.
    It does NOT search or rank candidates.
    """

    requested_count: int = Field(
        default=10,
        ge=1,
    )

    count_explicit: bool = Field(default=False)

    skills: list[str] = Field(
        default_factory=list,
    )

    roles: list[str] = Field(
        default_factory=list,
    )

    companies: list[str] = Field(
        default_factory=list,
    )

    location: str | None = Field(default=None)

    min_experience_years: float | None = Field(
        default=None,
        ge=0,
    )

    max_experience_years: float | None = Field(
        default=None,
        ge=0,
    )

    semantic_requirements: list[str] = Field(
        default_factory=list,
    )

    requirements: list[SearchRequirement] = Field(default_factory=list)


class RoutingPacket(BaseModel):
    """
    Final output of the search layer.

    Retrieval layers will consume this object later.
    """

    query: str

    specification: SearchSpecification

    route: SearchRoute

    structured_requirements: dict = Field(
        default_factory=dict,
    )

    semantic_requirements: list[str] = Field(
        default_factory=list,
    )

    @property
    def requirements(self) -> list[SearchRequirement]:
        """Expose the canonical graph directly to Intelligence Layer callers."""
        return self.specification.requirements

from typing import Any, Literal

from pydantic import BaseModel, Field


SearchRoute = Literal["STRUCTURED", "SEMANTIC", "HYBRID"]

RequirementType = str

RequirementRelationship = Literal[
    "AND",
    "OR",
    "SAME_EXPERIENCE",
    "SAME_PROJECT",
]

LocationScope = Literal[
    "CANDIDATE",
    "EXPERIENCE",
]


class SearchRequirement(BaseModel):
    """
    One recruiter requirement and the information needed to resolve it.

    Important distinction:
    - original_text = exactly what the recruiter expressed
    - normalized_text = cleaned representation of that expression
    - equivalent_terms = high-confidence terms with the same meaning
    - semantic_expansions = broader/related expressions useful for semantic retrieval

    The LLM may propose interpretations and expansions, but it does not
    decide whether a candidate actually satisfies the requirement.
    """

    id: str

    original_text: str = Field(
        description="The requirement as expressed by the recruiter.",
    )

    normalized_text: str = Field(
        description=(
            "A cleaned representation of that expression. "
            "Do not replace the recruiter's intent with a different role, "
            "skill, company, or concept."
        ),
    )

    type: RequirementType

    mandatory: bool = True

    match_mode: Literal["HARD", "SOFT"] | None = None

    source_of_truth: str | None = None

    capabilities: list[str] = Field(
        default_factory=list,
    )

    dependencies: list[str] = Field(
        default_factory=list,
    )

    related_requirements: list[str] = Field(
        default_factory=list,
    )

    group_id: str | None = None

    relationship: RequirementRelationship = "AND"

    negated: bool = False

    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )

    field: str | None = None

    value: (
        str
        | int
        | float
        | bool
        | list[str]
        | dict[str, Any]
        | None
    ) = None

    canonical_value: str | None = None

    # High-confidence equivalents that represent the same intent.
    #
    # Example:
    # "software developer" ->
    # [
    #     "software developer",
    #     "software engineer",
    #     "software development engineer",
    #     "SDE"
    # ]
    equivalent_terms: list[str] = Field(
        default_factory=list,
        description=(
            "High-confidence equivalent terms that can represent the "
            "same recruiter intent during retrieval."
        ),
    )

    # Broader or semantically related phrases that may support
    # semantic retrieval but are NOT necessarily exact equivalents.
    semantic_expansions: list[str] = Field(
        default_factory=list,
        description=(
            "Broader or related expressions that may provide useful "
            "semantic evidence. These must not silently replace the "
            "original requirement."
        ),
    )

    # Optional relaxed value used by deterministic search policy.
    #
    # Example:
    # Recruiter asks for 0-1 years:
    #
    # value = {"min": 0, "max": 1}
    # soft_value = {"min": 0, "max": 2}
    #
    # The LLM should NOT decide this tolerance.
    # The search policy should populate/use it deterministically.
    soft_value: (
        str
        | int
        | float
        | bool
        | list[str]
        | dict[str, Any]
        | None
    ) = Field(
        default=None,
        description=(
            "Optional relaxed value used for soft matching. "
            "This must not replace or alter the original requirement."
        ),
    )

    # ------------------------------------------------------------
    # LOCATION SCOPE
    # ------------------------------------------------------------
    #
    # This distinguishes:
    #
    # "software developer at TCS Pune"
    #
    # from:
    #
    # "software developer who worked at TCS in Pune"
    #
    # In the first case, Pune normally refers to the candidate's
    # location.
    #
    # In the second case, Pune refers to the location of the
    # relevant employment/experience record.
    #
    # None means the requirement is not a location requirement.
    location_scope: LocationScope | None = Field(
        default=None,
        description=(
            "Defines what the location refers to. "
            "CANDIDATE means the candidate's general/current location. "
            "EXPERIENCE means the location of the relevant employment "
            "or experience record. Leave null when the requirement "
            "is not location-related."
        ),
    )

    min_experience_exclusive: bool = False

    temporal_window_months: int | None = Field(
        default=None,
        ge=0,
    )

    minimum_relevant_experience_months: int | None = Field(
        default=None,
        ge=0,
    )


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
        description=(
            "Whether the recruiter explicitly requested a result count."
        ),
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
        description="Location requested by the recruiter.",
    )

    location_scope: LocationScope | None = Field(
        default=None,
        description=(
            "Defines whether the requested location applies to the "
            "candidate or to a relevant employment/experience record."
        ),
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
        description=(
            "Explicitly disclosed defaults inferred from recruiter wording."
        ),
    )

    requirements: list[SearchRequirement] = Field(
        default_factory=list,
        description=(
            "Extensible requirement graph extracted from the query."
        ),
    )

    route: SearchRoute = Field(
        default="STRUCTURED",
        description=(
            "Search route selected after classification."
        ),
    )


class ParsedQuery(BaseModel):
    """
    LLM output before routing.

    The LLM understands the recruiter's language and proposes
    structured requirements and retrieval expansions.

    It does NOT search, rank, or qualify candidates.
    """

    requested_count: int = Field(
        default=10,
        ge=1,
    )

    count_explicit: bool = Field(
        default=False,
    )

    skills: list[str] = Field(
        default_factory=list,
    )

    roles: list[str] = Field(
        default_factory=list,
    )

    companies: list[str] = Field(
        default_factory=list,
    )

    location: str | None = Field(
        default=None,
    )

    location_scope: LocationScope | None = Field(
        default=None,
        description=(
            "Whether the requested location refers to the candidate "
            "or to a relevant employment/experience record."
        ),
    )

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

    requirements: list[SearchRequirement] = Field(
        default_factory=list,
    )


class RoutingPacket(BaseModel):
    """
    Final output of the search layer.

    Retrieval layers consume this object after query understanding
    and validation have completed.

    The packet carries the interpreted requirements and routing
    information. Deterministic retrieval/scoring logic decides
    whether a candidate actually satisfies those requirements.
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
        """Expose the canonical requirement graph to search-layer callers."""
        return self.specification.requirements
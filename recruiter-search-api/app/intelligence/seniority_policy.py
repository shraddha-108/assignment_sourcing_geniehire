
from dataclasses import dataclass
from typing import Literal


SeniorityLevel = Literal[
    "FRESHER",
    "JUNIOR",
    "MID",
    "SENIOR",
    "LEAD",
]

ExperienceScope = Literal[
    "OVERALL",
    "RELEVANT_ROLE",
]

ExperienceFit = Literal[
    "PREFERRED",
    "ACCEPTABLE",
    "OUTSIDE",
]


@dataclass(frozen=True)
class SeniorityPolicy:
    """
    Defines the experience expectations for a seniority level.

    All experience boundaries are represented in months.
    Maximum None means there is no upper limit.
    """

    seniority: SeniorityLevel

    preferred_min_months: int
    preferred_max_months: int | None

    acceptable_min_months: int
    acceptable_max_months: int | None

    experience_scope: ExperienceScope


# Central seniority policy configuration.
# These are initial product defaults, not universal industry standards.

SENIORITY_POLICIES: dict[str, SeniorityPolicy] = {
    "FRESHER": SeniorityPolicy(
        seniority="FRESHER",
        preferred_min_months=0,
        preferred_max_months=12,
        acceptable_min_months=0,
        acceptable_max_months=24,
        experience_scope="OVERALL",
    ),

    "JUNIOR": SeniorityPolicy(
        seniority="JUNIOR",
        preferred_min_months=12,
        preferred_max_months=36,
        acceptable_min_months=6,
        acceptable_max_months=48,
        experience_scope="OVERALL",
    ),

    "MID": SeniorityPolicy(
        seniority="MID",
        preferred_min_months=36,
        preferred_max_months=72,
        acceptable_min_months=24,
        acceptable_max_months=96,
        experience_scope="RELEVANT_ROLE",
    ),

    "SENIOR": SeniorityPolicy(
        seniority="SENIOR",
        preferred_min_months=72,
        preferred_max_months=120,
        acceptable_min_months=60,
        acceptable_max_months=144,
        experience_scope="RELEVANT_ROLE",
    ),

    "LEAD": SeniorityPolicy(
        seniority="LEAD",
        preferred_min_months=96,
        preferred_max_months=144,
        acceptable_min_months=84,
        acceptable_max_months=None,
        experience_scope="RELEVANT_ROLE",
    ),
}


def normalize_seniority(seniority: str) -> str:
    """Normalize a seniority label to its canonical representation."""

    return seniority.strip().upper().replace("-", "_").replace(" ", "_")


def get_seniority_policy(seniority: str) -> SeniorityPolicy:
    """
    Return the configured policy for a seniority level.

    Raises:
        ValueError: If the seniority level is unsupported.
    """

    normalized = normalize_seniority(seniority)

    policy = SENIORITY_POLICIES.get(normalized)

    if policy is None:
        raise ValueError(
            f"Unsupported seniority level: {seniority}"
        )

    return policy


def classify_experience_fit(
    experience_months: int,
    policy: SeniorityPolicy,
) -> ExperienceFit:
    """
    Classify candidate experience against a seniority policy.

    PREFERRED:
        Experience falls inside the preferred range.

    ACCEPTABLE:
        Experience falls outside the preferred range but inside
        the acceptable range.

    OUTSIDE:
        Experience falls outside the acceptable range.
    """

    if experience_months < 0:
        raise ValueError("Experience months cannot be negative.")

    preferred_min = policy.preferred_min_months
    preferred_max = policy.preferred_max_months

    acceptable_min = policy.acceptable_min_months
    acceptable_max = policy.acceptable_max_months

    # Check preferred range first.
    preferred_match = (
        experience_months >= preferred_min
        and (
            preferred_max is None
            or experience_months <= preferred_max
        )
    )

    if preferred_match:
        return "PREFERRED"

    # Check acceptable range.
    acceptable_match = (
        experience_months >= acceptable_min
        and (
            acceptable_max is None
            or experience_months <= acceptable_max
        )
    )

    if acceptable_match:
        return "ACCEPTABLE"

    return "OUTSIDE"

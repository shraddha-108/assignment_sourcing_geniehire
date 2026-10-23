from typing import Literal

from pydantic import BaseModel, Field

from search.classifier import (
    SearchRequirement,
    StructuredRequirements,
)


class RoutingPacket(BaseModel):
    original_query: str
    requested_count: int = Field(ge=1)
    count_explicit: bool

    route: Literal[
        "STRUCTURED",
        "SEMANTIC",
        "HYBRID",
    ]

    requirements: list[SearchRequirement] = Field(
        default_factory=list
    )

    structured_requirements: StructuredRequirements

    semantic_requirement: str | None = None

    route_reason: str
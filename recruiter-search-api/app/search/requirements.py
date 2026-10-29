"""Graph normalization helpers shared by query understanding and routing."""

from app.search.schema import SearchRequirement
from app.search.normalization import (
    canonical_term,
    equivalent_terms,
    explicit_soft_requirement_ids,
    expand_semantic_requirement,
    requirement_kind,
)


_DIRECTIONAL_RELATIONSHIPS = {
    "DEPENDS_ON", "SAME_SOURCE", "TEMPORALLY_RELATED_TO"
}


def normalize_requirement_graph(
    requirements: list[SearchRequirement],
    query: str | None = None,
) -> list[SearchRequirement]:
    """Normalize requirement modes, aliases, and dependency direction."""
    by_id = {requirement.id: requirement for requirement in requirements}
    explicitly_soft = explicit_soft_requirement_ids(query or "", requirements)
    for requirement in requirements:
        requirement.match_mode = "SOFT" if requirement.id in explicitly_soft else "HARD"
        requirement.mandatory = requirement.match_mode == "HARD"
        kind = requirement_kind(requirement)
        value = requirement.value if isinstance(requirement.value, str) else None
        if value and kind:
            requirement.canonical_value = canonical_term(value, kind)
            requirement.equivalent_terms = equivalent_terms(value, kind)
            requirement.value = requirement.canonical_value
            requirement.normalized_text = requirement.canonical_value.casefold()
        if ("semantic_evidence_retrieval" in requirement.capabilities
                or requirement.type.upper() == "SEMANTIC"):
            semantic_text = value or requirement.original_text
            expanded = expand_semantic_requirement(semantic_text)
            requirement.semantic_expansions = [expanded] if expanded != semantic_text else []
        if requirement.relationship.upper() in _DIRECTIONAL_RELATIONSHIPS:
            requirement.dependencies = list(dict.fromkeys(
                requirement.dependencies + requirement.related_requirements
            ))

    directed_pairs = {
        (requirement.id, dependency)
        for requirement in requirements
        for dependency in requirement.dependencies
    }
    for requirement in requirements:
        requirement.dependencies = [dependency for dependency in requirement.dependencies if dependency in by_id]
        requirement.related_requirements = [related for related in requirement.related_requirements if related in by_id]
        requirement.related_requirements = [
            related_id
            for related_id in requirement.related_requirements
            if related_id in by_id
            and related_id not in requirement.dependencies
            and (related_id, requirement.id) not in directed_pairs
        ]
    return requirements

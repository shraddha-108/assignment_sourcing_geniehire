"""Graph normalization helpers shared by query understanding and routing."""

from app.search.schema import SearchRequirement
from app.search.normalization import (
    canonical_term,
    equivalent_terms,
    explicit_soft_requirement_ids,
    expand_semantic_requirement,
    requirement_kind,
)


# These relationships describe directional dependencies.
# They are kept here only as normalization behavior.
#
# IMPORTANT:
# The schema/parser should only emit valid public relationship values:
#   AND
#   OR
#   SAME_EXPERIENCE
#   SAME_PROJECT
#
# If legacy/older parser output contains one of these directional values,
# normalize it into dependency information rather than exposing the value
# as the final relationship.
_DIRECTIONAL_RELATIONSHIPS = {
    "DEPENDS_ON",
    "SAME_SOURCE",
    "TEMPORALLY_RELATED_TO",
}


def normalize_requirement_graph(
    requirements: list[SearchRequirement],
    query: str | None = None,
) -> list[SearchRequirement]:
    """
    Normalize requirement modes, aliases, semantic expansions,
    and dependency direction.

    Important distinction:

    - original_text:
        What the recruiter actually expressed.

    - normalized_text:
        Cleaned representation that preserves the recruiter's intent.

    - value:
        The structured value used by the retrieval layer.
        This must NOT silently replace the recruiter's term with a
        different canonical term.

    - canonical_value:
        Internal canonical representation useful for normalization
        and comparison.

    - equivalent_terms:
        High-confidence alternatives that represent the same intent.

    The canonical representation must never overwrite `value`.

    Example:

        recruiter query:
            "software developer"

        result:

            original_text:
                "software developer"

            normalized_text:
                "software developer"

            value:
                "software developer"

            canonical_value:
                "software engineer"

            equivalent_terms:
                [
                    "software developer",
                    "software engineer",
                    "software development engineer",
                    "SDE"
                ]

    This allows retrieval to search using the recruiter's original
    intent plus controlled equivalents without rewriting the query.
    """

    by_id = {
        requirement.id: requirement
        for requirement in requirements
    }

    explicitly_soft = explicit_soft_requirement_ids(
        query or "",
        requirements,
    )

    for requirement in requirements:
        # ------------------------------------------------------------
        # HARD / SOFT MODE
        # ------------------------------------------------------------

        requirement.match_mode = (
            "SOFT"
            if requirement.id in explicitly_soft
            else "HARD"
        )

        requirement.mandatory = (
            requirement.match_mode == "HARD"
        )

        # ------------------------------------------------------------
        # REQUIREMENT KIND
        # ------------------------------------------------------------

        kind = requirement_kind(requirement)

        value = (
            requirement.value
            if isinstance(requirement.value, str)
            else None
        )

        if value and kind:
            # --------------------------------------------------------
            # IMPORTANT:
            #
            # canonical_value is allowed to be different from value.
            #
            # Example:
            #
            # value            = "software developer"
            # canonical_value  = "software engineer"
            #
            # But we MUST NOT replace value with canonical_value.
            # --------------------------------------------------------

            requirement.canonical_value = canonical_term(
                value,
                kind,
            )

            # Get controlled equivalents from the normalization layer.
            #
            # The original value should always remain available as an
            # equivalent term too.
            generated_equivalents = equivalent_terms(
                value,
                kind,
            )

            terms = [
                value,
                *generated_equivalents,
                *requirement.equivalent_terms,
            ]

            # Deduplicate while preserving order.
            deduped_terms: list[str] = []
            seen_terms: set[str] = set()

            for term in terms:
                if not isinstance(term, str):
                    continue

                cleaned_term = term.strip()

                if not cleaned_term:
                    continue

                key = cleaned_term.casefold()

                if key in seen_terms:
                    continue

                seen_terms.add(key)
                deduped_terms.append(cleaned_term)

            requirement.equivalent_terms = deduped_terms

            # --------------------------------------------------------
            # DO NOT DO THIS:
            #
            # requirement.value = requirement.canonical_value
            #
            # That would turn:
            #
            # "software developer"
            #
            # into:
            #
            # "software engineer"
            #
            # and lose the recruiter's original structured value.
            # --------------------------------------------------------

            # Preserve the recruiter's wording while cleaning only
            # whitespace/casing-related noise.
            #
            # Do not replace it with canonical_value.
            requirement.value = value.strip()

            requirement.normalized_text = value.strip()

        # ------------------------------------------------------------
        # SEMANTIC EXPANSIONS
        # ------------------------------------------------------------

        if (
            "semantic_evidence_retrieval"
            in requirement.capabilities
            or requirement.type.upper() == "SEMANTIC"
        ):
            semantic_text = (
                value
                or requirement.original_text
            )

            expanded = expand_semantic_requirement(
                semantic_text
            )

            requirement.semantic_expansions = (
                [expanded]
                if expanded != semantic_text
                else []
            )

        # ------------------------------------------------------------
        # LEGACY DIRECTIONAL RELATIONSHIPS
        # ------------------------------------------------------------

        if (
            requirement.relationship.upper()
            in _DIRECTIONAL_RELATIONSHIPS
        ):
            requirement.dependencies = list(
                dict.fromkeys(
                    requirement.dependencies
                    + requirement.related_requirements
                )
            )

            # Keep the final relationship schema-compatible.
            #
            # Dependency information is represented through
            # `dependencies`, not through an invented relationship
            # value such as SAME_SOURCE.
            requirement.relationship = "AND"

    # ------------------------------------------------------------
    # BUILD DIRECTED DEPENDENCY PAIRS
    # ------------------------------------------------------------

    directed_pairs = {
        (
            requirement.id,
            dependency,
        )
        for requirement in requirements
        for dependency in requirement.dependencies
    }

    # ------------------------------------------------------------
    # CLEAN REFERENCES
    # ------------------------------------------------------------

    for requirement in requirements:
        requirement.dependencies = [
            dependency
            for dependency in requirement.dependencies
            if dependency in by_id
        ]

        requirement.related_requirements = [
            related
            for related in requirement.related_requirements
            if related in by_id
        ]

        # Remove related requirements that are already represented
        # as dependencies or that create a reverse directed pair.
        requirement.related_requirements = [
            related_id
            for related_id in requirement.related_requirements
            if (
                related_id in by_id
                and related_id not in requirement.dependencies
                and (related_id, requirement.id)
                not in directed_pairs
            )
        ]

    return requirements
from app.search.schema import ParsedQuery, SearchRoute


def classify_query(parsed_query: ParsedQuery) -> SearchRoute:
    """
    Classify a parsed recruiter query into a retrieval route.

    STRUCTURED:
        PostgreSQL is sufficient.

    SEMANTIC:
        Qdrant semantic retrieval is required.

    HYBRID:
        Both PostgreSQL and Qdrant are required.
    """

    requirements = list(parsed_query.requirements or [])
    if requirements:
        has_structured_requirements = any(
            set(requirement.capabilities) & {
                "structured_candidate_lookup", "structured_experience_lookup"
            }
            for requirement in requirements
        )
        has_semantic_requirements = any(
            "semantic_evidence_retrieval" in requirement.capabilities
            for requirement in requirements
        )
        if has_structured_requirements and has_semantic_requirements:
            return "HYBRID"
        if has_semantic_requirements:
            return "SEMANTIC"
        return "STRUCTURED"

    has_structured_requirements = any(
        [
            bool(parsed_query.skills),
            bool(parsed_query.roles),
            bool(parsed_query.companies),
            bool(parsed_query.location),
            parsed_query.min_experience_years is not None,
            parsed_query.max_experience_years is not None,
        ]
    )

    has_semantic_requirements = bool(
        parsed_query.semantic_requirements
    )

    if has_structured_requirements and has_semantic_requirements:
        return "HYBRID"

    if has_semantic_requirements:
        return "SEMANTIC"

    return "STRUCTURED"

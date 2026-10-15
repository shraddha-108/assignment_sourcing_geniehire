def route_query(parsed: dict) -> str:

    structured = parsed[
        "structured_requirements"
    ]

    semantic_requirement = parsed.get(
        "semantic_requirement"
    )

    has_structured = any(
        [
            bool(structured.get("skills")),
            structured.get("recency_months") is not None,
            structured.get("experience_min_years") is not None,
        ]
    )

    has_semantic = bool(
        semantic_requirement
    )

    if has_structured and has_semantic:
        return "HYBRID"

    if has_semantic:
        return "SEMANTIC"

    return "STRUCTURED"
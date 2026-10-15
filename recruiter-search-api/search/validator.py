from typing import Any


def validate_parsed_query(
    parsed: dict[str, Any],
) -> dict[str, Any]:

    errors = []

    requested_count = parsed.get("requested_count")

    if not isinstance(requested_count, int):
        errors.append(
            "requested_count must be an integer"
        )
    elif requested_count < 1:
        errors.append(
            "requested_count must be at least 1"
        )

    structured = parsed.get(
        "structured_requirements"
    )

    if not isinstance(structured, dict):
        errors.append(
            "structured_requirements must be an object"
        )
        structured = {}

    skills = structured.get("skills", [])

    if not isinstance(skills, list):
        errors.append(
            "skills must be a list"
        )

    recency_months = structured.get(
        "recency_months"
    )

    if recency_months is not None:

        if not isinstance(recency_months, int):
            errors.append(
                "recency_months must be an integer"
            )

        elif recency_months < 0:
            errors.append(
                "recency_months cannot be negative"
            )

    experience_min_years = structured.get(
        "experience_min_years"
    )

    if experience_min_years is not None:

        if not isinstance(
            experience_min_years,
            int,
        ):
            errors.append(
                "experience_min_years must be an integer"
            )

        elif experience_min_years < 0:
            errors.append(
                "experience_min_years cannot be negative"
            )

    semantic_requirement = parsed.get(
        "semantic_requirement"
    )

    if (
        semantic_requirement is not None
        and not isinstance(
            semantic_requirement,
            str,
        )
    ):
        errors.append(
            "semantic_requirement must be a string or null"
        )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }
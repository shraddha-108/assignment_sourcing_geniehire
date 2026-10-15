from search.parser import parse_query
from search.validator import validate_parsed_query
from search.router import route_query
from search.exclusion import extract_exclusions


def build_routing_packet(
    query: str,
    known_skills: list[str],
) -> dict:

    parsed = parse_query(
        query=query,
        known_skills=known_skills,
    )

    validation = validate_parsed_query(
        parsed
    )

    if not validation["valid"]:
        return {
            "valid": False,
            "errors": validation["errors"],
        }

    exclusions = extract_exclusions(
        query
    )

    route = route_query(parsed)

    return {
        "valid": True,
        "route": route,
        "routing_packet": {
            "original_query": query,
            "requested_count": parsed[
                "requested_count"
            ],
            "structured_requirements": parsed[
                "structured_requirements"
            ],
            "semantic_requirement": parsed[
                "semantic_requirement"
            ],
            "exclusions": exclusions,
        },
    }
from search.classifier import (
    classify_search_intent,
)

from search.validator import (
    RoutingPacket,
)


def build_routing_packet(
    query: str,
    known_skills: list[str],
) -> dict:

    original_query = query.strip()

    intent = classify_search_intent(
        query=original_query,
        known_skills=known_skills,
    )

    routing_packet = RoutingPacket(
        original_query=original_query,
        requested_count=intent.requested_count,
        count_explicit=intent.count_explicit,
        route=intent.route,
        requirements=intent.requirements,
        structured_requirements=(
            intent.structured_requirements
        ),
        semantic_requirement=(
            intent.semantic_requirement
        ),
        route_reason=intent.reason,
    )

    return {
        "valid": True,
        "errors": [],
        "route": routing_packet.route,
        "routing_packet": routing_packet.model_dump(),
    }
from search.service import build_routing_packet


KNOWN_SKILLS = [
    "python",
    "sql",
    "java",
    "react",
    "javascript",
    "typescript",
    "postgresql",
    "nodejs",
    "fastapi",
    "django",
]


def test_structured_query():

    result = build_routing_packet(
        "Find 10 Python developers recently",
        KNOWN_SKILLS,
    )

    assert result["valid"] is True
    assert result["route"] == "STRUCTURED"

    packet = result["routing_packet"]

    assert packet["requested_count"] == 10
    assert packet["structured_requirements"]["skills"] == [
        "python"
    ]
    assert packet["semantic_requirement"] is None


def test_semantic_query():

    result = build_routing_packet(
        "Find candidates who built AI products",
        KNOWN_SKILLS,
    )

    assert result["valid"] is True
    assert result["route"] == "SEMANTIC"

    packet = result["routing_packet"]

    assert packet["semantic_requirement"] is not None


def test_hybrid_query():

    result = build_routing_packet(
        "Find 20 Python developers with 3+ years of experience building AI products",
        KNOWN_SKILLS,
    )

    assert result["valid"] is True
    assert result["route"] == "HYBRID"

    packet = result["routing_packet"]

    assert packet["requested_count"] == 20

    assert packet["structured_requirements"]["skills"] == [
        "python"
    ]

    assert (
        packet["structured_requirements"][
            "experience_min_years"
        ]
        == 3
    )

    assert packet["semantic_requirement"] is not None
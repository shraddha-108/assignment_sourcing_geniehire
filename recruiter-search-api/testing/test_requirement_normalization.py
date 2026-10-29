import pytest
from types import SimpleNamespace
from datetime import date

from app.intelligence.ranker import rank_candidates
from app.search.normalization import (
    canonical_term,
    equivalent_terms,
    expand_semantic_requirement,
    parse_explicit_experience_bounds,
    normalize_explicit_semantic_or,
    industry_evidence_matches,
)
from app.search.requirements import normalize_requirement_graph
from app.search.schema import SearchRequirement
from app.search.schema import ParsedQuery
from app.database.location_utils import location_matches


@pytest.mark.parametrize(
    "title",
    ["SDE", "Software Engineer", "Software Development Engineer"],
)
def test_sde_title_variants_share_canonical_role(title):
    assert canonical_term(title, "role") == "software engineer"
    assert set(equivalent_terms(title, "role")) == {
        "software engineer", "sde", "software development engineer", "software developer"
    }


def test_skill_aliases_are_exact_and_do_not_confuse_java_with_javascript():
    assert canonical_term("JS", "skill") == "javascript"
    assert canonical_term("Postgres", "skill") == "postgresql"
    assert canonical_term("Javascipt", "skill") == "javascript"
    assert equivalent_terms("Java", "skill") == ["java"]


@pytest.mark.parametrize("requested", ["Pune", "Maharashtra", "India"])
def test_location_hierarchy_matches_city_state_and_country(requested):
    location = SimpleNamespace(
        city="Pune", normalized_city="pune",
        state="Maharashtra", normalized_state="maharashtra",
        country="India", normalized_country="india",
    )
    assert location_matches(requested, location)


def test_preference_language_only_softens_the_named_requirement():
    requirements = [
        SearchRequirement(id="role", original_text="Python developer", normalized_text="python developer",
                          type="STRUCTURED", field="roles", value="Software Developer"),
        SearchRequirement(id="experience", original_text="5+ years", normalized_text="5 years",
                          type="STRUCTURED", field="experience", value={"min_experience_years": 5}),
        SearchRequirement(id="aws", original_text="AWS", normalized_text="aws",
                          type="STRUCTURED", field="skills", value="AWS"),
    ]
    normalize_requirement_graph(requirements, "Python developer with 5+ years, preferably AWS")
    assert [item.match_mode for item in requirements] == ["HARD", "HARD", "SOFT"]
    assert [item.mandatory for item in requirements] == [True, True, False]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("0-1 years", (0.0, 1.0, False)),
        ("0–1 years", (0.0, 1.0, False)),
        ("1-3 years", (1.0, 3.0, False)),
        ("5+ years", (5.0, None, False)),
        ("at least 5 years", (5.0, None, False)),
        ("more than 5 years", (5.0, None, True)),
    ],
)
def test_explicit_experience_bounds_keep_the_requested_boundary(query, expected):
    result = parse_explicit_experience_bounds(query)
    assert result is not None
    assert (
        result["min_experience_years"],
        result["max_experience_years"],
        result["min_experience_exclusive"],
    ) == expected


@pytest.mark.parametrize(
    "query",
    [
        "implemented SAP for financial process optimization",
        "built AI products for healthcare",
        "worked on AWS migration projects",
    ],
)
def test_semantic_expansion_preserves_the_original_relationship_clause(query):
    expanded = expand_semantic_requirement(query)
    assert expanded.startswith(query)
    assert "alternatives, not extra requirements" in expanded


def test_ai_product_expansion_handles_natural_word_order_without_splitting_clause():
    query = "built products with AI for healthcare"
    expanded = expand_semantic_requirement(query)
    assert expanded.startswith(query)
    assert "production AI applications" in expanded


def test_explicit_semantic_or_keeps_each_alternative_in_one_shared_group():
    combined = SearchRequirement(
        id="semantic_all", original_text="built products with AI or worked with LangChain",
        normalized_text="built products with ai or worked with langchain",
        type="SEMANTIC", field="semantic_requirements",
        capabilities=["semantic_evidence_retrieval", "evidence_validation"],
        value="built products with AI or who has worked with LangChain framework",
    )
    langchain = SearchRequirement(
        id="skill_langchain", original_text="LangChain", normalized_text="langchain",
        type="STRUCTURED", field="skills", source_of_truth="candidate_skill",
        capabilities=["structured_candidate_lookup"], value="LangChain",
    )
    requirements = [combined, langchain]
    semantic = normalize_explicit_semantic_or(
        "candidates who has built products with AI or who has worked with LangChain framework",
        requirements,
        [combined.value],
    )
    group = {item.id: item for item in requirements}
    assert semantic == ["built products with AI", "worked with LangChain framework"]
    assert group["skill_langchain"].relationship == "OR"
    assert group["skill_langchain"].group_id == group["explicit_or_semantic_all_semantic_1"].group_id
    assert all(item.relationship == "OR" for item in requirements)


def test_ranker_removes_no_match_and_places_all_matches_before_partials():
    candidates = [
        {"candidate_id": 1, "score": 0.99,
         "validation": {"valid": True, "match_status": "PARTIAL_MATCH"}},
        {"candidate_id": 2, "score": 0.60,
         "validation": {"valid": True, "match_status": "MATCH"}},
        {"candidate_id": 3, "score": 1.00,
         "validation": {"valid": False, "match_status": "NO_MATCH"}},
    ]
    ranked = rank_candidates(candidates, requested_count=10)
    assert [item["candidate_id"] for item in ranked] == [2, 1]


@pytest.mark.parametrize(
    ("query", "llm_role"),
    [
        ("SDE with 5+ years", "SDE"),
        ("Software Engineer with 5+ years", "Software Engineer"),
        ("Software Development Engineer with 5+ years", "Software Development Engineer"),
    ],
)
def test_routing_packet_canonicalizes_equivalent_role_and_numeric_intent(monkeypatch, query, llm_role):
    import app.search.service as service

    monkeypatch.setattr(service, "parse_query", lambda _: ParsedQuery(
        roles=[llm_role], min_experience_years=1,
    ))
    packet = service.build_routing_packet(query)
    assert packet.specification.roles == ["software engineer"]
    assert packet.specification.min_experience_years == 5


def test_preferred_aws_is_soft_but_required_aws_is_hard(monkeypatch):
    import app.search.service as service

    monkeypatch.setattr(service, "parse_query", lambda _: ParsedQuery(
        skills=["Python", "AWS"], roles=["developer"], min_experience_years=1,
    ))
    preferred = service.build_routing_packet(
        "Python developer with 5+ years, preferably AWS"
    )
    required = service.build_routing_packet(
        "Python developer with 5+ years, must have AWS"
    )
    preferred_aws = next(item for item in preferred.requirements if item.value == "AWS")
    required_aws = next(item for item in required.requirements if item.value == "AWS")
    assert preferred_aws.match_mode == "SOFT"
    assert not preferred_aws.mandatory
    assert required_aws.match_mode == "HARD"
    assert required_aws.mandatory


def test_routing_preserves_cross_type_explicit_or_as_one_alternative_group(monkeypatch):
    import app.search.service as service

    monkeypatch.setattr(service, "parse_query", lambda _: ParsedQuery(
        skills=["LangChain"],
        semantic_requirements=["built products with AI or who has worked with LangChain framework"],
    ))
    packet = service.build_routing_packet(
        "candidates who has built products with AI or who has worked with LangChain framework"
    )
    alternatives = [
        item for item in packet.requirements
        if item.group_id and item.relationship == "OR"
    ]
    assert len(alternatives) == 3
    assert {item.field for item in alternatives} == {"skills", "semantic_requirements"}
    assert len({item.group_id for item in alternatives}) == 1
    assert packet.semantic_requirements == [
        "built products with AI", "worked with LangChain framework"
    ]


@pytest.mark.parametrize(
    ("candidate_id", "expected"),
    [(1, True), (2, True), (3, False)],
)
def test_mixed_structured_semantic_or_qualifies_either_alternative(monkeypatch, candidate_id, expected):
    import app.intelligence.validator as validator

    group = "explicit_or"
    requirements = [
        SearchRequirement(
            id="ai_products", original_text="built products with AI",
            normalized_text="built products with ai", type="SEMANTIC",
            field="semantic_requirements", value="built products with AI",
            capabilities=["semantic_evidence_retrieval", "evidence_validation"],
            group_id=group, relationship="OR",
        ),
        SearchRequirement(
            id="langchain_work", original_text="worked with LangChain framework",
            normalized_text="worked with langchain framework", type="SEMANTIC",
            field="semantic_requirements", value="worked with LangChain framework",
            capabilities=["semantic_evidence_retrieval", "evidence_validation"],
            group_id=group, relationship="OR",
        ),
        SearchRequirement(
            id="langchain_skill", original_text="LangChain", normalized_text="langchain",
            type="STRUCTURED", field="skills", value="LangChain",
            capabilities=["structured_candidate_lookup"],
            group_id=group, relationship="OR",
        ),
    ]

    def structured_check(*, db, candidate_id, requirements, evidence):
        is_skill_alternative = requirements.get("skills") == ["LangChain"]
        passed = (candidate_id == 1) if is_skill_alternative else True
        matches = ([{"type": "skill", "candidate_value": "LangChain", "evidence": []}]
                   if passed and is_skill_alternative else [])
        return passed, [], matches, []

    def semantic_check(*, candidate_id, semantic_requirements, evidence):
        if not semantic_requirements:
            return True, [], [], []
        passed = candidate_id == 2
        matches = [{"type": "semantic", "requirement": semantic_requirements[0],
                    "matched": passed, "evidence": evidence[:1] if passed else []}]
        return passed, [] if passed else [{"type": "SEMANTIC"}], evidence[:1] if passed else [], matches

    monkeypatch.setattr(validator, "validate_structured_requirements", structured_check)
    monkeypatch.setattr(validator, "validate_semantic_requirements", semantic_check)
    monkeypatch.setattr(validator, "validate_relational_requirements", lambda **_: ([], []))
    monkeypatch.setattr(validator, "validate_temporal_requirements", lambda **_: ([], []))

    result = validator.validate_candidate(
        db=None, candidate_id=candidate_id, structured_requirements={"skills": ["LangChain"]},
        semantic_requirements=["built products with AI", "worked with LangChain framework"],
        evidence=[{"text": "Built AI products", "evidence_type": "project"}],
        requirements_graph=requirements,
        candidate_semantic_scores=(
            {"built products with ai": 0.8, "worked with langchain framework": 0.8}
            if candidate_id == 2 else {}
        ),
        candidate_semantic_min_score=0.5,
    )
    assert result["valid"] is expected


def test_relevant_experience_stops_before_a_separate_and_clause_and_deduplicates(monkeypatch):
    import app.search.service as service

    duplicate_semantics = [
        SearchRequirement(
            id=f"semantic_{index}",
            original_text="AI and who knows Java",
            normalized_text="ai and who knows java",
            type="SEMANTIC", field="semantic_requirements",
            value="AI and who knows Java",
            capabilities=["semantic_evidence_retrieval", "evidence_validation"],
        )
        for index in (1, 2)
    ]
    monkeypatch.setattr(service, "parse_query", lambda _: ParsedQuery(
        skills=["Java"], min_experience_years=2,
        semantic_requirements=["AI and who knows Java"],
        requirements=duplicate_semantics,
    ))

    packet = service.build_routing_packet(
        "candidates who has 2 years of experience in AI and who knows Java"
    )
    semantic = [item for item in packet.requirements if item.type == "SEMANTIC"]
    assert packet.semantic_requirements == ["AI"]
    assert len(semantic) == 1
    assert semantic[0].value == "AI"
    assert semantic[0].minimum_relevant_experience_months == 24
    assert packet.specification.skills == ["java"]
    assert packet.specification.min_experience_years is None


def test_industry_evidence_uses_dated_employer_context_for_relevant_tenure(monkeypatch):
    import app.intelligence.validator as validator
    from app.intelligence.pipeline import _add_dated_industry_evidence

    assert industry_evidence_matches("Finance Manager at AXISCADES TECHNONOLOGIES LTD", "IT industry")
    assert not industry_evidence_matches("Finance Manager at Bluefish Pharmaceuticals", "IT industry")
    assert "software" in expand_semantic_requirement("IT industry")

    dated_role = SimpleNamespace(
        id=91, role=SimpleNamespace(title="Finance Manager"),
        company=SimpleNamespace(name="AXISCADES TECHNONOLOGIES LTD"),
        description="Managed finance operations.",
        start_date=date(2020, 1, 1), end_date=date(2023, 1, 1), is_current=False,
    )
    assembled = {7: []}
    _add_dated_industry_evidence(
        assembled, {7: SimpleNamespace(experiences=[dated_role])}, ["IT industry"]
    )
    assert len(assembled[7]) == 1
    assert assembled[7][0]["source_kind"] == "experience_record"

    experience = SimpleNamespace(
        id=91, candidate_id=7, start_date=date(2020, 1, 1),
        end_date=date(2023, 1, 1), is_current=False,
        duration_months=36, role=None, company=None,
    )
    requirement = SearchRequirement(
        id="it_tenure", original_text="2 years relevant experience in IT industry",
        normalized_text="it industry", type="SEMANTIC", field="semantic_requirements",
        value="IT industry", minimum_relevant_experience_months=24,
        capabilities=["semantic_evidence_retrieval", "evidence_validation"],
    )
    monkeypatch.setattr(validator, "validate_structured_requirements",
                        lambda **_: (True, [], [], []))
    monkeypatch.setattr(validator, "_resolve_experience_source", lambda *args: experience)
    monkeypatch.setattr(validator, "validate_relational_requirements", lambda **_: ([], []))
    monkeypatch.setattr(validator, "validate_temporal_requirements", lambda **_: ([], []))
    result = validator.validate_candidate(
        db=None, candidate_id=7, structured_requirements={},
        semantic_requirements=["IT industry"],
        evidence=[{
            "source_kind": "experience_record", "experience_id": 91,
            "evidence_type": "experience",
            "text": "Finance Manager at AXISCADES TECHNONOLOGIES LTD",
        }],
        requirements_graph=[requirement],
        candidate_semantic_scores={"it industry": 0.9},
        candidate_semantic_min_score=0.5,
    )
    assert result["valid"], result["failures"]
    tenure = next(item for item in result["matched_requirements"]
                  if item["type"] == "relevant_experience")
    assert tenure["matched"]


def test_industry_evidence_uses_dated_employer_context_for_relevant_tenure(monkeypatch):
    import app.intelligence.validator as validator

    assert industry_evidence_matches("Finance Manager at AXISCADES TECHNONOLOGIES LTD", "IT industry")
    assert not industry_evidence_matches("Finance Manager at Bluefish Pharmaceuticals", "IT industry")
    assert "software" in expand_semantic_requirement("IT industry")

    experience = SimpleNamespace(
        id=91, candidate_id=7, start_date=date(2020, 1, 1),
        end_date=date(2023, 1, 1), is_current=False,
        duration_months=36, role=None, company=None,
    )
    requirement = SearchRequirement(
        id="it_tenure", original_text="2 years relevant experience in IT industry",
        normalized_text="it industry", type="SEMANTIC", field="semantic_requirements",
        value="IT industry", minimum_relevant_experience_months=24,
        capabilities=["semantic_evidence_retrieval", "evidence_validation"],
    )
    monkeypatch.setattr(validator, "validate_structured_requirements",
                        lambda **_: (True, [], [], []))
    monkeypatch.setattr(validator, "_resolve_experience_source", lambda *args: experience)
    monkeypatch.setattr(validator, "validate_relational_requirements", lambda **_: ([], []))
    monkeypatch.setattr(validator, "validate_temporal_requirements", lambda **_: ([], []))
    result = validator.validate_candidate(
        db=None, candidate_id=7, structured_requirements={},
        semantic_requirements=["IT industry"],
        evidence=[{
            "source_kind": "experience_record", "experience_id": 91,
            "evidence_type": "experience",
            "text": "Finance Manager at AXISCADES TECHNONOLOGIES LTD",
        }],
        requirements_graph=[requirement],
        candidate_semantic_scores={"it industry": 0.9},
        candidate_semantic_min_score=0.5,
    )
    assert result["valid"], result.get("failures")
    tenure = next(item for item in result["matched_requirements"]
                  if item["type"] == "relevant_experience")
    assert tenure["matched"]

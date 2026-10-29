from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.intelligence.planner import build_execution_plan, semantic_candidate_scope
from app.intelligence.observability import rejection_records
from app.intelligence.scorer import _requirement_fit
from app.intelligence.validator import (
    _supports_semantic_requirement,
    validate_relational_requirements,
    validate_semantic_requirements,
    validate_temporal_requirements,
)
from app.search.requirements import normalize_requirement_graph
from app.search.schema import SearchRequirement


def req(identifier, kind, capabilities, *, depends_on=None, mandatory=True, value=None,
        relationship="AND", months=None):
    return SearchRequirement(
        id=identifier,
        original_text=identifier,
        normalized_text=identifier,
        type=kind,
        mandatory=mandatory,
        capabilities=capabilities,
        dependencies=depends_on or [],
        relationship=relationship,
        value=value,
        temporal_window_months=months,
    )


def stage_order(plan):
    return [item["stage"] for item in plan["stages"]]


def test_structured_only_plan():
    plan = build_execution_plan([req("skill", "STRUCTURED", ["structured_candidate_lookup"])])
    assert "structured_filter" in stage_order(plan)
    assert "semantic_retrieval" not in stage_order(plan)


def test_semantic_only_plan():
    plan = build_execution_plan([req("project", "SEMANTIC", ["semantic_evidence_retrieval"])])
    assert stage_order(plan).index("semantic_retrieval") < stage_order(plan).index("evidence_validation")


def test_structured_and_semantic_plan_prefilters():
    plan = build_execution_plan([
        req("role", "STRUCTURED", ["structured_experience_lookup"]),
        req("work", "SEMANTIC", ["semantic_evidence_retrieval"]),
    ])
    assert stage_order(plan).index("structured_filter") < stage_order(plan).index("semantic_retrieval")


def test_temporal_stage_waits_for_its_semantic_dependency():
    plan = build_execution_plan([
        req("activity", "SEMANTIC", ["semantic_evidence_retrieval"]),
        req("time", "TEMPORAL", ["temporal_validation"], depends_on=["activity"]),
    ])
    assert stage_order(plan).index("semantic_retrieval") < stage_order(plan).index("temporal_validation")
    temporal = next(item for item in plan["stages"] if item["stage"] == "temporal_validation")
    assert "semantic_retrieval" in temporal["depends_on"]


def test_temporal_dependency_does_not_cycle_through_final_evidence_validation():
    plan = build_execution_plan([
        req("activity", "SEMANTIC", ["semantic_evidence_retrieval", "evidence_validation"]),
        req("time", "TEMPORAL", ["temporal_validation", "evidence_validation"],
            depends_on=["activity"]),
    ])
    ordered = stage_order(plan)
    assert ordered.index("semantic_retrieval") < ordered.index("temporal_validation")
    assert ordered.index("evidence_validation") < ordered.index("temporal_validation")
    assert ordered.index("temporal_validation") < ordered.index("qualification")


def test_temporal_requirement_keeps_a_directional_dependency_and_time_window():
    activity = req("activity", "SEMANTIC",
        ["semantic_evidence_retrieval", "evidence_validation"])
    activity.related_requirements = ["time"]
    temporal = req("time", "TEMPORAL", ["temporal_validation"],
        depends_on=["activity"], relationship="TEMPORALLY_RELATED_TO", months=12)
    temporal.related_requirements = ["activity"]

    graph = normalize_requirement_graph([activity, temporal])
    assert graph[0].related_requirements == []
    assert graph[1].dependencies == ["activity"]
    assert graph[1].temporal_window_months == 12

    plan = build_execution_plan(graph)
    ordered = stage_order(plan)
    assert ordered.index("evidence_validation") < ordered.index("temporal_validation")
    assert ordered.index("temporal_validation") < ordered.index("qualification")


def test_multiple_semantic_requirements_share_a_stage():
    plan = build_execution_plan([
        req("project_a", "SEMANTIC", ["semantic_evidence_retrieval"]),
        req("project_b", "SEMANTIC", ["semantic_evidence_retrieval"]),
    ])
    semantic = next(item for item in plan["stages"] if item["stage"] == "semantic_retrieval")
    assert semantic["requirement_ids"] == ["project_a", "project_b"]


def test_multiple_structured_requirements_share_a_stage():
    plan = build_execution_plan([
        req("skill", "STRUCTURED", ["structured_candidate_lookup"]),
        req("role", "STRUCTURED", ["structured_experience_lookup"]),
    ])
    structured = next(item for item in plan["stages"] if item["stage"] == "structured_filter")
    assert structured["requirement_ids"] == ["skill", "role"]


def test_dependency_order_is_graph_driven_and_cycle_is_rejected():
    plan = build_execution_plan([
        req("later", "SEMANTIC", ["semantic_evidence_retrieval"], depends_on=["earlier"]),
        req("earlier", "SEMANTIC", ["semantic_evidence_retrieval"]),
    ])
    assert plan["requirement_order"] == ["earlier", "later"]
    with pytest.raises(ValueError, match="cycle"):
        build_execution_plan([
            req("a", "SEMANTIC", ["semantic_evidence_retrieval"], depends_on=["b"]),
            req("b", "SEMANTIC", ["semantic_evidence_retrieval"], depends_on=["a"]),
        ])


def test_hard_and_soft_requirements_are_kept_explicit():
    hard = req("must", "STRUCTURED", ["structured_candidate_lookup"])
    soft = req("prefer", "SEMANTIC", ["semantic_evidence_retrieval"], mandatory=False)
    plan = build_execution_plan([hard, soft])
    assert hard.mandatory is True and soft.mandatory is False
    assert "semantic_retrieval" in stage_order(plan)


def test_soft_requirements_influence_fit_without_becoming_hard_failures():
    assert _requirement_fit([
        {"type": "skill", "mandatory": False, "matched": True},
        {"type": "location", "mandatory": False, "matched": False},
    ]) == 0.5


def test_semantic_scope_applies_structured_candidates_before_vector_search():
    assert semantic_candidate_scope(True, [4, 9]) == [4, 9]
    assert semantic_candidate_scope(True, []) == []
    assert semantic_candidate_scope(False, [4, 9]) is None


def test_plan_explains_capability_and_dependency_order():
    plan = build_execution_plan([
        req("work", "SEMANTIC", ["semantic_evidence_retrieval"]),
        req("time", "TEMPORAL", ["temporal_validation"], depends_on=["work"]),
    ])
    assert any("semantic_evidence_retrieval" in line for line in plan["explanation"])
    assert any("depends on work" in line for line in plan["explanation"])


@pytest.mark.parametrize("query_wording", [
    "a backend engineer who has delivered product recommendations",
    "someone in backend development with recommendation-product work",
])
def test_ambiguous_wordings_can_share_the_same_capability_graph(query_wording):
    # Query text is deliberately not inspected by the planner. Query
    # understanding supplies normalized requirements and capabilities.
    graph = [
        req("backend", "STRUCTURED", ["structured_experience_lookup"]),
        req("recommendation_work", "SEMANTIC", ["semantic_evidence_retrieval"]),
    ]
    graph[1].original_text = query_wording
    plan = build_execution_plan(graph)
    assert [stage["stage"] for stage in plan["stages"]] == [
        "structured_filter", "semantic_retrieval", "evidence_validation", "qualification", "ranking"
    ]


def test_rejection_trace_identifies_candidate_requirement_and_stage():
    records = rejection_records(47, "evidence_validation", [{
        "requirement_id": "project_work", "reason": "No supporting evidence found",
    }])
    assert records[0]["candidate_id"] == 47
    assert records[0]["requirement_id"] == "project_work"
    assert records[0]["stage"] == "evidence_validation"
    assert records[0]["reason"] == "No supporting evidence found"


class FakeDB:
    def __init__(self, section, experiences):
        self.section = section
        self.experiences = experiences

    def get(self, model, identifier):
        return self.section if identifier == self.section.id else None

    def scalars(self, query):
        return SimpleNamespace(all=lambda: self.experiences)


def test_temporal_validation_uses_dated_matched_source_only():
    activity = "Built a recommendation engine using collaborative filtering."
    section = SimpleNamespace(id=7, section_type="experience", content=activity)
    experience = SimpleNamespace(
        description=activity,
        end_date=date.today() - timedelta(days=40),
        is_current=False,
        start_date=date.today() - timedelta(days=200),
    )
    temporal = req("time", "TEMPORAL", ["temporal_validation"],
        depends_on=["activity"], months=6)
    semantic = req("activity", "SEMANTIC", ["semantic_evidence_retrieval"], value="Built recommendation engine")
    evidence = [{"evidence_type": "experience", "resume_section_id": 7,
        "requirement": "Built recommendation engine", "text": activity}]
    failures, matches = validate_temporal_requirements(FakeDB(section, [experience]), 12,
        [semantic, temporal], evidence)
    assert failures == []
    assert matches[0]["matched"] is True


def test_temporal_validation_fails_closed_when_source_has_no_date():
    activity = "Built a recommendation engine using collaborative filtering."
    section = SimpleNamespace(id=7, section_type="experience", content=activity)
    experience = SimpleNamespace(description=activity, end_date=None, is_current=False, start_date=None)
    temporal = req("time", "TEMPORAL", ["temporal_validation"],
        depends_on=["activity"], months=6)
    semantic = req("activity", "SEMANTIC", ["semantic_evidence_retrieval"], value="Built recommendation engine")
    evidence = [{"evidence_type": "experience", "resume_section_id": 7,
        "requirement": "Built recommendation engine", "text": activity}]
    failures, _ = validate_temporal_requirements(FakeDB(section, [experience]), 12,
        [semantic, temporal], evidence)
    assert failures and failures[0]["type"] == "TEMPORAL"


def test_same_source_relationship_resolves_against_dependency_evidence():
    left = req("left", "SEMANTIC", ["semantic_evidence_retrieval"], value="left")
    right = req("right", "STRUCTURED", ["structured_experience_lookup"], value="right")
    relation = req("same", "RELATIONAL", ["relationship_resolution"],
        depends_on=["left", "right"], relationship="SAME_SOURCE")
    evidence = [
        {"requirement": "left", "source_id": 44, "evidence_type": "project"},
        {"requirement": "right", "source_id": 44, "evidence_type": "project"},
    ]
    failures, matches = validate_relational_requirements(FakeDB(None, []), 8,
        [left, right, relation], evidence)
    assert failures == []
    assert matches[0]["matched"] is True


def test_cross_encoder_supports_paraphrases_without_literal_token_overlap():
    passage = "Architected a horizontally scaled platform distributed across fault-tolerant services."
    assert _supports_semantic_requirement(
        "designed scalable distributed systems", passage, "experience"
    ) is None
    assert _supports_semantic_requirement(
        "designed scalable distributed systems", passage, "experience", 0.2
    ) == passage
    assert _supports_semantic_requirement(
        "designed scalable distributed systems", passage, "experience", -0.2
    ) is None


def test_semantic_requirement_validation_uses_reranked_resume_evidence():
    passage = "Architected a horizontally scaled platform distributed across fault-tolerant services."
    valid, failures, supporting, matches = validate_semantic_requirements(
        candidate_id=17,
        semantic_requirements=["designed scalable distributed systems"],
        evidence=[{
            "candidate_id": 17,
            "evidence_id": 901,
            "evidence_type": "experience",
            "text": passage,
            "reranker_score": 0.2,
        }],
    )
    assert valid is True
    assert failures == []
    assert supporting[0]["evidence_id"] == 901
    assert supporting[0]["text"] == passage
    assert matches[0]["matched"] is True

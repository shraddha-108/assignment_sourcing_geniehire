import unittest
from unittest.mock import patch

from app.intelligence.pipeline import _mixed_structured_or_branches
from app.search.normalization import apply_explicit_boolean_operators
from app.search.schema import ParsedQuery
from app.search.service import (
    build_routing_packet,
    _deduplicate_structured_skill_requirements,
    _normalize_compound_structured_skills,
)
from app.search.schema import SearchRequirement


def skill_requirement(value="Java", original_text=None):
    return SearchRequirement(
        id="skill",
        original_text=original_text or value,
        normalized_text=value.casefold(),
        type="STRUCTURED",
        capabilities=["structured_candidate_lookup"],
        field="skill",
        value=value,
    )


def semantic_requirement(value="worked on machine learning projects"):
    return SearchRequirement(
        id="project",
        original_text=value,
        normalized_text=value.casefold(),
        type="SEMANTIC",
        capabilities=["semantic_evidence_retrieval", "evidence_validation"],
        field="semantic_requirements",
        value=value,
    )


class ExplicitBooleanOperatorTests(unittest.TestCase):
    def test_or_groups_structured_and_semantic_alternatives(self):
        skill = skill_requirement()
        project = semantic_requirement()

        apply_explicit_boolean_operators(
            "Java or worked on machine learning projects",
            [skill, project],
        )

        self.assertEqual(skill.group_id, project.group_id)
        self.assertEqual(skill.relationship, "OR")
        self.assertEqual(project.relationship, "OR")
        self.assertFalse(skill.negated)
        self.assertFalse(project.negated)

    def test_and_remains_a_conjunction(self):
        skill = skill_requirement()
        project = semantic_requirement()

        apply_explicit_boolean_operators(
            "Java and worked on machine learning projects",
            [skill, project],
        )

        self.assertIsNone(skill.group_id)
        self.assertIsNone(project.group_id)
        self.assertEqual(skill.relationship, "AND")
        self.assertEqual(project.relationship, "AND")

    def test_not_marks_only_the_excluded_requirement(self):
        skill = skill_requirement()
        project = semantic_requirement()

        apply_explicit_boolean_operators(
            "Java and not worked on machine learning projects",
            [skill, project],
        )

        self.assertFalse(skill.negated)
        self.assertTrue(project.negated)
        self.assertIsNone(project.group_id)

    def test_or_not_creates_a_disjunction_with_an_exclusion(self):
        skill = skill_requirement()
        project = semantic_requirement()

        apply_explicit_boolean_operators(
            "Java or not worked on machine learning projects",
            [skill, project],
        )

        self.assertFalse(skill.negated)
        self.assertTrue(project.negated)
        self.assertEqual(skill.group_id, project.group_id)
        self.assertEqual(project.relationship, "OR")

    def test_compound_structured_text_does_not_hide_semantic_or_branch(self):
        skill = skill_requirement(
            value="Java or also worked on machine learning projects",
            original_text="Java or also worked on machine learning projects",
        )
        project = semantic_requirement()

        apply_explicit_boolean_operators(
            "Java or also worked on machine learning projects",
            [skill, project],
        )

        self.assertEqual(skill.group_id, project.group_id)
        self.assertEqual(skill.relationship, "OR")
        self.assertEqual(project.relationship, "OR")

    def test_mixed_or_retrieves_the_structured_alternative(self):
        skill = skill_requirement()
        project = semantic_requirement()
        apply_explicit_boolean_operators(
            "Java or worked on machine learning projects",
            [skill, project],
        )

        branches = _mixed_structured_or_branches(
            [skill, project],
            {"skills": [], "roles": [], "companies": []},
        )

        self.assertEqual(len(branches), 1)
        self.assertIn("java", [value.casefold() for value in branches[0]["skills"]])

    def test_parser_skill_that_swallowed_semantic_or_clause_is_repaired(self):
        query = "candidate who knows java or also worked on machine learning projects"
        compound_skill = skill_requirement(
            value="Java or also worked on machine learning projects",
            original_text="Java or also worked on machine learning projects",
        )
        duplicate_java = skill_requirement()
        project = semantic_requirement()
        requirements = [compound_skill, duplicate_java, project]

        _normalize_compound_structured_skills(["Java"], requirements)
        _deduplicate_structured_skill_requirements(requirements)
        apply_explicit_boolean_operators(query, requirements)

        self.assertEqual(len(requirements), 2)
        self.assertEqual(compound_skill.value, "Java")
        self.assertEqual(compound_skill.group_id, project.group_id)
        self.assertEqual(compound_skill.relationship, "OR")
        self.assertEqual(project.relationship, "OR")

    @patch("app.search.service.classify_query", return_value="HYBRID")
    @patch("app.search.service.parse_query")
    def test_exact_candidate_who_knows_or_worked_query_routes_as_or(
        self, parse_query, _classify_query
    ):
        query = "candidate who knows java or also worked on machine learning projects"
        compound_skill = skill_requirement(
            value="Java or also worked on machine learning projects",
            original_text="Java or also worked on machine learning projects",
        )
        project = semantic_requirement()
        parse_query.return_value = ParsedQuery(
            skills=["Java"],
            semantic_requirements=[project.value],
            requirements=[compound_skill, project],
        )

        packet = build_routing_packet(query)
        skill_nodes = [
            item for item in packet.requirements
            if (item.field or "").casefold() in {"skill", "skills"}
        ]
        semantic_nodes = [
            item for item in packet.requirements
            if "semantic_evidence_retrieval" in item.capabilities
        ]

        self.assertEqual(len(skill_nodes), 1)
        self.assertEqual(skill_nodes[0].value.casefold(), "java")
        self.assertEqual(len(semantic_nodes), 1)
        self.assertEqual(skill_nodes[0].group_id, semantic_nodes[0].group_id)
        self.assertEqual(skill_nodes[0].relationship, "OR")
        self.assertEqual(semantic_nodes[0].relationship, "OR")


if __name__ == "__main__":
    unittest.main()

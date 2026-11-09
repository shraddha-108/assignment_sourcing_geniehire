import unittest

from app.intelligence.retriever import _role_matches as retrieved_role_matches
from app.intelligence.validator import _role_matches as validated_role_matches
from app.search.normalization import role_matches
from app.search.requirements import normalize_requirement_graph
from app.search.schema import SearchRequirement


class RoleMatchingTests(unittest.TestCase):
    def test_backend_developer_matches_backend_title_variants(self):
        self.assertTrue(role_matches("backend developer", "Senior Backend Engineer"))
        self.assertTrue(
            retrieved_role_matches("backend developer", "Senior Backend Engineer")
        )
        self.assertTrue(
            validated_role_matches("backend developer", "Senior Backend Engineer")
        )
        self.assertTrue(
            role_matches("backend developer", "Software Engineer - Backend")
        )
        self.assertTrue(role_matches("back-end developer", "Back End Software Engineer"))

    def test_frontend_developer_matches_frontend_title_variants(self):
        self.assertTrue(
            role_matches("frontend developer", "Senior Front-end Engineer")
        )
        self.assertTrue(
            role_matches("frontend developer", "Software Engineer - Frontend")
        )
        self.assertFalse(role_matches("frontend developer", "Backend Developer"))

    def test_cloud_developer_matches_cloud_development_titles_only(self):
        self.assertTrue(role_matches("cloud developer", "Senior Cloud Engineer"))
        self.assertTrue(
            role_matches("cloud developer", "Cloud Platform Developer")
        )
        self.assertFalse(role_matches("cloud developer", "Cloud Architect"))
        self.assertFalse(role_matches("cloud developer", "DevOps Engineer"))

    def test_generic_developer_includes_specialties_but_not_qa(self):
        self.assertTrue(role_matches("developer", "Full Stack Developer"))
        self.assertTrue(role_matches("developer", "Backend Software Developer"))
        self.assertFalse(role_matches("developer", "QA Automation Developer"))

    def test_explicit_role_is_a_hard_requirement_by_default(self):
        requirement = SearchRequirement(
            id="backend-role",
            original_text="backend developer",
            normalized_text="backend developer",
            type="STRUCTURED",
            field="roles",
            value="backend developer",
            capabilities=["structured_experience_lookup"],
        )

        normalize_requirement_graph([requirement], "backend developer")

        self.assertEqual(requirement.match_mode, "HARD")
        self.assertTrue(requirement.mandatory)

    def test_explicit_preference_can_make_role_soft(self):
        requirement = SearchRequirement(
            id="backend-role",
            original_text="backend developer",
            normalized_text="backend developer",
            type="STRUCTURED",
            field="roles",
            value="backend developer",
            capabilities=["structured_experience_lookup"],
        )

        normalize_requirement_graph(
            [requirement],
            "preferably backend developer",
        )

        self.assertEqual(requirement.match_mode, "SOFT")
        self.assertFalse(requirement.mandatory)


if __name__ == "__main__":
    unittest.main()

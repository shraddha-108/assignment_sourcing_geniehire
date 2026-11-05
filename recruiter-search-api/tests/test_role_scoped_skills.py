import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.database.models
from app.database.base import Base
from app.database.models.candidate import Candidate
from app.database.models.candidate_skill import CandidateSkill
from app.database.models.experience import Experience
from app.database.models.experience_skill import ExperienceSkill
from app.database.models.role import Role
from app.database.models.skill import Skill
from app.intelligence.retriever import retrieve_structured_candidates
from app.intelligence.validator import validate_structured_requirements


class RoleScopedSkillTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        self.candidate = Candidate(name="React skill only on profile")
        self.role = Role(title="Software Developer", normalized_title="software developer")
        self.skill = Skill(name="React", normalized_name="react")
        self.session.add_all([self.candidate, self.role, self.skill])
        self.session.flush()
        self.experience = Experience(
            candidate_id=self.candidate.id,
            role_id=self.role.id,
        )
        self.session.add_all(
            [
                self.experience,
                CandidateSkill(
                    candidate_id=self.candidate.id,
                    skill_id=self.skill.id,
                ),
            ]
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_profile_skill_without_role_experience_is_not_a_match(self):
        requirements = {"roles": ["developer"], "skills": ["React"]}

        valid, failures, matched, _ = validate_structured_requirements(
            db=self.session,
            candidate_id=self.candidate.id,
            requirements=requirements,
            evidence=[],
        )

        self.assertFalse(valid)
        self.assertIn("SKILL", {failure["type"] for failure in failures})
        self.assertFalse(any(item["type"] == "skill" for item in matched))
        self.assertEqual(
            retrieve_structured_candidates(self.session, requirements),
            [],
        )

    def test_skill_linked_to_matching_role_experience_is_a_match(self):
        self.session.add(
            ExperienceSkill(
                candidate_id=self.candidate.id,
                experience_id=self.experience.id,
                skill_id=self.skill.id,
                evidence="Built React user interfaces",
            )
        )
        self.session.commit()
        requirements = {"roles": ["developer"], "skills": ["React"]}

        valid, failures, matched, evidence = validate_structured_requirements(
            db=self.session,
            candidate_id=self.candidate.id,
            requirements=requirements,
            evidence=[],
        )

        self.assertTrue(valid)
        self.assertEqual(failures, [])
        self.assertEqual([item["type"] for item in matched], ["skill", "role"])
        self.assertEqual(evidence[0]["text"], "Built React user interfaces")
        results = retrieve_structured_candidates(self.session, requirements)
        self.assertEqual([item["candidate_id"] for item in results], [self.candidate.id])

    def test_skill_only_search_keeps_candidate_profile_skill_matching(self):
        requirements = {"skills": ["React"]}

        valid, failures, matched, _ = validate_structured_requirements(
            db=self.session,
            candidate_id=self.candidate.id,
            requirements=requirements,
            evidence=[],
        )

        self.assertTrue(valid)
        self.assertEqual(failures, [])
        self.assertEqual([item["type"] for item in matched], ["skill"])


if __name__ == "__main__":
    unittest.main()

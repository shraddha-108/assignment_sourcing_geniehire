import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.intelligence.validator.nli_verifier import (
    format_hypothesis,
    verify_evidence_entailment,
)
from app.intelligence.validator import (
    _supports_semantic_requirement,
    validate_semantic_requirements,
)


class NliValidationTests(unittest.TestCase):
    def test_format_hypothesis(self):
        self.assertEqual(
            format_hypothesis("built products with AI"),
            "The candidate has built products with AI.",
        )
        self.assertEqual(
            format_hypothesis("worked in B2B sales"),
            "The candidate has worked in B2B sales.",
        )
        self.assertEqual(
            format_hypothesis("experience designing distributed systems"),
            "The candidate has experience designing distributed systems.",
        )
        self.assertEqual(
            format_hypothesis("Python"),
            "The candidate has experience with Python.",
        )

    def test_rejects_q006_software_engineer_on_b2b_sales(self):
        """Candidate 107 (SWE who built a B2B platform) should NOT qualify as B2B sales."""
        req = "worked in B2B sales"
        swe_b2b_sentence = "Developed and maintained B2B equipment rental platform using Angular and Node.js."
        swe_b2b_text = (
            "Developed and maintained B2B equipment rental platform using Angular and Node.js. "
            "Integrated payment gateways and managed MongoDB databases."
        )

        # The specific B2B platform sentence directly contradicts B2B sales
        single_res = verify_evidence_entailment(swe_b2b_sentence, req)
        self.assertFalse(single_res["matched"])
        self.assertGreater(single_res["contradiction_score"], 0.80)

        # The full passage as a whole fails to qualify
        nli_res = verify_evidence_entailment(swe_b2b_text, req)
        self.assertFalse(nli_res["matched"])
        self.assertLess(nli_res["confidence"], 0.05)

        # In validator:
        supported = _supports_semantic_requirement(
            requirement=req,
            evidence_text=swe_b2b_text,
            evidence_type="experience",
            reranker_score=0.45,
        )
        self.assertIsNone(supported)

        passed, failures, _, _ = validate_semantic_requirements(
            candidate_id=107,
            semantic_requirements=[req],
            evidence=[{
                "candidate_id": 107,
                "evidence_type": "experience",
                "text": swe_b2b_text,
                "reranker_score": 0.45,
            }],
        )
        self.assertFalse(passed)
        self.assertTrue(any(f["type"] == "SEMANTIC" for f in failures))

    def test_accepts_q006_true_b2b_salesperson(self):
        """Candidate 126 (True B2B sales) must qualify with high entailment confidence."""
        req = "worked in B2B sales"
        sales_text = (
            "Achieved 140% of sales quota selling enterprise B2B SaaS solutions to mid-market accounts. "
            "Led outbound prospecting and conducted product demos."
        )

        nli_res = verify_evidence_entailment(sales_text, req)
        self.assertTrue(nli_res["matched"])
        self.assertGreaterEqual(nli_res["confidence"], 0.85)

        passed, failures, supporting, matches = validate_semantic_requirements(
            candidate_id=126,
            semantic_requirements=[req],
            evidence=[{
                "candidate_id": 126,
                "evidence_type": "experience",
                "text": sales_text,
                "reranker_score": 0.55,
            }],
        )
        self.assertTrue(passed)
        self.assertEqual(len(failures), 0)
        self.assertEqual(len(supporting), 1)
        self.assertTrue(supporting[0].get("nli_verified"))

    def test_distinguishes_ai_builder_from_ai_recruiter(self):
        """AI builder qualifies for 'built products with AI', AI recruiter is rejected."""
        req = "built products with AI"
        builder_text = (
            "Spearheaded development of real-time conversational AI agents using LangChain, OpenAI API, and PyTorch."
        )
        recruiter_text = (
            "Senior Technical Recruiter sourcing GenAI researchers, computer vision specialists, and machine learning engineers."
        )

        builder_passed, _, _, _ = validate_semantic_requirements(
            candidate_id=1,
            semantic_requirements=[req],
            evidence=[{
                "candidate_id": 1,
                "evidence_type": "experience",
                "text": builder_text,
                "reranker_score": 0.60,
            }],
        )
        self.assertTrue(builder_passed)

        recruiter_passed, _, _, _ = validate_semantic_requirements(
            candidate_id=2,
            semantic_requirements=[req],
            evidence=[{
                "candidate_id": 2,
                "evidence_type": "experience",
                "text": recruiter_text,
                "reranker_score": 0.50,
            }],
        )
        self.assertFalse(recruiter_passed)

        # Sneaky HR recruiter using build verbs for talent pipelines
        sneaky_hr_text = "Built talent acquisition pipelines for machine learning products."
        sneaky_passed, _, _, _ = validate_semantic_requirements(
            candidate_id=3,
            semantic_requirements=[req],
            evidence=[{
                "candidate_id": 3,
                "evidence_type": "experience",
                "text": sneaky_hr_text,
                "reranker_score": 0.50,
            }],
        )
        self.assertFalse(sneaky_passed)


if __name__ == "__main__":
    unittest.main()

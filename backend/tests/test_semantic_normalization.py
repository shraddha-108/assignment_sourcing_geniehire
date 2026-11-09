import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.intelligence.validator import (
    _supports_semantic_requirement,
    customer_relationship_partial_evidence,
    validate_semantic_requirements,
)
from app.intelligence.pipeline import (
    _allow_customer_relationship_partial_match,
    _allow_relevant_duration_partial_match,
    _structured_filter_for_requirement,
)
from app.intelligence.retriever import retrieve_semantic
from app.search.normalization import (
    canonicalize_semantic_requirement,
    company_name_matches,
    expand_semantic_requirement,
)


class SemanticNormalizationTests(unittest.TestCase):
    def test_company_aliases_match_full_names_and_parenthesized_acronyms(self):
        aliases = [
            "TCS",
            "Tata Consultancy Services",
            "Tata Consultancy Services Ltd",
            "Tata Consultancy Services Limited",
        ]

        self.assertTrue(company_name_matches("TCS", aliases))
        self.assertTrue(company_name_matches("Tata Consultancy Services", aliases))
        self.assertTrue(company_name_matches("Tata Consultancy Services(TCS)", aliases))
        self.assertTrue(company_name_matches("Tata Consultancy Services (TCS)", aliases))
        self.assertFalse(company_name_matches("TCS Consulting Group", aliases))

    def test_company_structured_filter_preserves_parser_aliases(self):
        requirement = SimpleNamespace(
            id="company",
            field="companies",
            value="TCS",
            equivalent_terms=[
                "TCS",
                "Tata Consultancy Services",
                "Tata Consultancy Services Limited",
            ],
        )

        self.assertEqual(
            _structured_filter_for_requirement(requirement),
            {
                "companies": ["TCS"],
                "company_aliases": {
                    "TCS": requirement.equivalent_terms,
                },
            },
        )

    def test_singular_and_plural_ml_project_queries_use_the_same_retrieval_wording(self):
        singular = "worked with machine learning project"
        plural = "worked with machine learning projects"

        self.assertEqual(canonicalize_semantic_requirement(singular), plural)
        self.assertEqual(
            expand_semantic_requirement(singular),
            expand_semantic_requirement(plural),
        )

    @patch("app.intelligence.retriever.retrieve_semantic_candidates")
    def test_singular_and_plural_use_the_same_reranker_query(self, retrieve):
        retrieve.return_value = [{
            "candidate_id": 1,
            "evidence_id": "project-1",
            "evidence_type": "project",
            "text": "Built an ML project.",
            "retrieval_score": 1.0,
        }]

        singular = retrieve_semantic(
            query="worked with machine learning project",
            semantic_requirements=["worked with machine learning project"],
        )
        plural = retrieve_semantic(
            query="worked with machine learning projects",
            semantic_requirements=["worked with machine learning projects"],
        )

        self.assertEqual(
            singular[0]["reranker_query"],
            plural[0]["reranker_query"],
        )

    def test_singular_and_plural_ml_project_requirements_accept_the_same_evidence(self):
        evidence = [{
            "evidence_type": "project",
            "text": (
                "Developed and compared CNN and DenseNet models for skin lesion "
                "classification using deep learning techniques in Python."
            ),
        }]

        for requirement in (
            "worked with machine learning project",
            "worked with machine learning projects",
        ):
            valid, failures, supporting_evidence, _ = validate_semantic_requirements(
                candidate_id=1,
                semantic_requirements=[requirement],
                evidence=evidence,
            )
            self.assertTrue(valid)
            self.assertEqual(failures, [])
            self.assertTrue(supporting_evidence)

    def test_customer_relationship_management_expands_to_business_domain_terms(self):
        expanded = expand_semantic_requirement(
            "8 years of experience with customer relationship management"
        )

        self.assertIn("account management", expanded)
        self.assertIn("Salesforce", expanded)
        self.assertIn("customer success", expanded)

    def test_customer_relationship_management_accepts_nontechnical_synonyms(self):
        requirement = "customer relationship management"

        for evidence in (
            "Managed client relationships and enterprise accounts.",
            "Led account management and customer retention initiatives.",
            "Administered Salesforce CRM for customer engagement.",
        ):
            with self.subTest(evidence=evidence):
                self.assertIsNotNone(
                    _supports_semantic_requirement(
                        requirement=requirement,
                        evidence_text=evidence,
                        evidence_type="experience",
                    )
                )

        self.assertIsNone(
            _supports_semantic_requirement(
                requirement=requirement,
                evidence_text="Built REST APIs and managed software deployments.",
                evidence_type="experience",
            )
        )

    def test_generic_dynamics_and_finance_operations_are_not_confirmed_crm_matches(self):
        requirement = "experience with customer relationship management"
        for evidence in (
            "Led implementation of Microsoft Dynamics 365 Finance & Operations.",
            "Configured D365 F&O modules for finance workflows.",
            "Developed solutions using Dynamics AX.",
            "Tools & Platforms: LinkedIn Sales Navigator, HubSpot, Apollo.",
            "AI-DRIVEN CRM: HyeGro.",
        ):
            with self.subTest(evidence=evidence):
                self.assertIsNone(
                    _supports_semantic_requirement(
                        requirement=requirement,
                        evidence_text=evidence,
                        evidence_type="experience",
                    )
                )
                self.assertIsNotNone(
                    customer_relationship_partial_evidence(
                        requirement,
                        evidence,
                        "experience",
                    )
                )

    def test_crm_specific_dynamics_evidence_remains_a_full_match(self):
        for evidence in (
            "Implemented Microsoft Dynamics 365 CRM for sales teams.",
            "Customer Success Manager for strategic accounts.",
            "Strengthened client relationships through effective communication.",
        ):
            with self.subTest(evidence=evidence):
                self.assertIsNotNone(
                    _supports_semantic_requirement(
                        requirement="experience with customer relationship management",
                        evidence_text=evidence,
                        evidence_type="experience",
                    )
                )

    def test_platform_listing_without_work_context_is_not_a_full_match(self):
        requirement = "experience with customer relationship management"
        evidence = "Tools & Platforms: LinkedIn Sales Navigator, HubSpot, Apollo."
        self.assertIsNone(
            _supports_semantic_requirement(
                requirement=requirement,
                evidence_text=evidence,
                evidence_type="experience",
            )
        )
        self.assertIsNotNone(
            customer_relationship_partial_evidence(
                requirement,
                evidence,
                "experience",
            )
        )

    def test_dynamics_adjacent_candidate_is_labeled_partial_not_match(self):
        requirement = SimpleNamespace(
            id="crm",
            value="experience with customer relationship management",
            original_text="experience with customer relationship management",
            capabilities=["semantic_evidence_retrieval"],
        )
        evidence = [{
            "evidence_type": "experience",
            "text": "Led implementation of Microsoft Dynamics 365 Finance & Operations.",
        }]
        validation = {
            "valid": False,
            "match_status": "NO_MATCH",
            "failures": [{
                "type": "SEMANTIC",
                "required": requirement.value,
            }],
            "matched_requirements": [{
                "type": "semantic",
                "requirement_id": "crm",
                "requirement": requirement.original_text,
                "matched": False,
                "evidence": [],
            }],
            "requirement_statuses": [{
                "requirement_id": "crm",
                "matched": False,
                "status": "NO_MATCH",
            }],
        }

        self.assertTrue(
            _allow_customer_relationship_partial_match(
                validation,
                evidence,
                [requirement],
            )
        )
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["match_status"], "PARTIAL_MATCH")
        self.assertEqual(
            validation["matched_requirements"][0]["status"],
            "PARTIAL_MATCH",
        )
        self.assertFalse(validation["matched_requirements"][0]["matched"])
        self.assertEqual(
            validation["requirement_statuses"][0]["status"],
            "PARTIAL_MATCH",
        )

    def test_undated_relevant_tenure_keeps_evidenced_experienced_candidate_as_partial(self):
        requirement = SimpleNamespace(
            id="r1",
            minimum_relevant_experience_months=96,
        )
        validation = {
            "valid": False,
            "match_status": "NO_MATCH",
            "failures": [{
                "type": "EXPERIENCE_SCOPE",
                "requirement_id": "r1",
            }],
            "matched_requirements": [
                {
                    "type": "semantic",
                    "requirement_id": "r1",
                    "matched": True,
                    "evidence": [{"text": "Managed client relationships."}],
                },
                {
                    "type": "relevant_experience",
                    "requirement_id": "r1",
                    "matched": False,
                },
            ],
        }

        self.assertTrue(
            _allow_relevant_duration_partial_match(
                validation,
                total_experience_months=120,
                requirements=[requirement],
            )
        )
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["match_status"], "PARTIAL_MATCH")
        self.assertEqual(
            validation["matched_requirements"][1]["status"],
            "PARTIAL_MATCH",
        )

    def test_partial_fallback_requires_total_years_and_confirmed_semantic_evidence(self):
        requirement = SimpleNamespace(
            id="r1",
            minimum_relevant_experience_months=96,
        )
        base_validation = {
            "valid": False,
            "failures": [{
                "type": "EXPERIENCE_SCOPE",
                "requirement_id": "r1",
            }],
            "matched_requirements": [{
                "type": "semantic",
                "requirement_id": "r1",
                "matched": True,
                "evidence": [{"text": "CRM experience"}],
            }],
        }

        self.assertFalse(
            _allow_relevant_duration_partial_match(
                {**base_validation},
                total_experience_months=95,
                requirements=[requirement],
            )
        )
        self.assertFalse(
            _allow_relevant_duration_partial_match(
                {
                    **base_validation,
                    "matched_requirements": [{
                        "type": "semantic",
                        "requirement_id": "r1",
                        "matched": False,
                        "evidence": [],
                    }],
                },
                total_experience_months=120,
                requirements=[requirement],
            )
        )


if __name__ == "__main__":
    unittest.main()

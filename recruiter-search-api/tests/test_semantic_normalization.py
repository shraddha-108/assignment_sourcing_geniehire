import unittest
from unittest.mock import patch

from app.intelligence.validator import validate_semantic_requirements
from app.intelligence.retriever import retrieve_semantic
from app.search.normalization import (
    canonicalize_semantic_requirement,
    expand_semantic_requirement,
)


class SemanticNormalizationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

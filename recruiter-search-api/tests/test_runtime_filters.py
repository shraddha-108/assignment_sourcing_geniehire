import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import (
    RuntimeFilters,
    SENIORITY_BANDS,
    _apply_runtime_filters,
    _intersect_experience_ranges,
    _seniority_ranges,
)
from app.database.base import Base
import app.database.models
from app.database.models.candidate import Candidate
from app.database.models.experience import Experience
from app.database.models.resume import Resume
from app.database.models.role import Role
from app.intelligence.pipeline import _mixed_structured_or_branches
from app.intelligence.retriever import retrieve_structured_candidates
from app.search.schema import RoutingPacket, SearchSpecification


def routing_packet(
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> RoutingPacket:
    specification = SearchSpecification(
        min_experience_years=minimum,
        max_experience_years=maximum,
    )
    return RoutingPacket(
        query="find candidates",
        specification=specification,
        route="STRUCTURED",
        structured_requirements={
            "min_experience_years": minimum,
            "max_experience_years": maximum,
            "companies": [],
        },
    )


class RuntimeSeniorityFilterTests(unittest.TestCase):
    def test_seniority_bands_have_one_backend_source_of_truth(self):
        self.assertEqual(
            SENIORITY_BANDS,
            {
                "entry": (0.0, 2.0),
                "mid": (3.0, 7.0),
                "senior": (8.0, None),
            },
        )
        self.assertEqual(
            _seniority_ranges(["entry", "MID", "unknown"]),
            [(0.0, 2.0), (3.0, 7.0)],
        )

    def test_inclusive_year_maxima_allow_fractional_year_intersections(self):
        self.assertEqual(
            _intersect_experience_ranges((0, 2), (2.5, 3)),
            (2.5, 2),
        )
        self.assertIsNone(_intersect_experience_ranges((0, 2), (3, 3)))

    def test_adjacent_selected_bands_remain_an_or_group(self):
        packet = _apply_runtime_filters(
            routing_packet(),
            RuntimeFilters(seniority=["entry", "mid"]),
        )
        requirements = packet.specification.requirements

        self.assertEqual(len(requirements), 2)
        self.assertEqual({item.group_id for item in requirements}, {"runtime_filter_seniority"})
        self.assertEqual({item.relationship for item in requirements}, {"OR"})
        self.assertEqual(
            [item.value for item in requirements],
            [
                {"min_experience_years": 0.0, "max_experience_years": 2.0},
                {"min_experience_years": 3.0, "max_experience_years": 7.0},
            ],
        )
        self.assertEqual(packet.specification.min_experience_years, 0)
        self.assertEqual(packet.specification.max_experience_years, 7)

    def test_non_adjacent_bands_remain_separate_or_alternatives(self):
        packet = _apply_runtime_filters(
            routing_packet(),
            RuntimeFilters(seniority=["entry", "senior"]),
        )

    def test_seniority_or_branches_do_not_widen_original_experience_bounds(self):
        packet = _apply_runtime_filters(
            routing_packet(minimum=5, maximum=10),
            RuntimeFilters(seniority=["entry", "senior"]),
        )
        branches = _mixed_structured_or_branches(
            packet.specification.requirements,
            {
                "min_experience_years": packet.specification.min_experience_years,
                "max_experience_years": packet.specification.max_experience_years,
                "skills": [],
                "roles": [],
                "companies": [],
            },
        )

        self.assertEqual(
            [
                (branch["min_experience_years"], branch["max_experience_years"])
                for branch in branches
            ],
            [(5, 2.0), (8.0, 10)],
        )

        self.assertEqual(len(packet.specification.requirements), 2)
        self.assertEqual(
            [item.value for item in packet.specification.requirements],
            [
                {"min_experience_years": 0.0, "max_experience_years": 2.0},
                {"min_experience_years": 8.0, "max_experience_years": None},
            ],
        )

    def test_experience_range_intersects_selected_bands_and_drops_empty_bands(self):
        packet = _apply_runtime_filters(
            routing_packet(),
            RuntimeFilters(
                seniority=["entry", "mid"],
                experience_min=2.5,
                experience_max=3,
            ),
        )

        self.assertEqual(
            [item.value for item in packet.specification.requirements],
            [
                {"min_experience_years": 2.5, "max_experience_years": 2.0},
                {"min_experience_years": 3.0, "max_experience_years": 3.0},
            ],
        )

    def test_disjoint_experience_and_seniority_raise_validation_error(self):
        with self.assertRaisesRegex(
            ValueError,
            "Experience range and seniority selection don't overlap\\.",
        ):
            _apply_runtime_filters(
                routing_packet(),
                RuntimeFilters(seniority=["entry"], experience_min=3),
            )

    def test_manual_experience_intersects_existing_query_bounds(self):
        packet = _apply_runtime_filters(
            routing_packet(minimum=4, maximum=9),
            RuntimeFilters(experience_min=5, experience_max=7),
        )

        self.assertEqual(packet.specification.min_experience_years, 5)
        self.assertEqual(packet.specification.max_experience_years, 7)
        self.assertEqual(
            packet.specification.requirements[0].value,
            {"min_experience_years": 5, "max_experience_years": 7},
        )

    def test_maximum_only_experience_filter_is_supported(self):
        packet = _apply_runtime_filters(
            routing_packet(),
            RuntimeFilters(experience_max=2),
        )

        self.assertIsNone(packet.specification.min_experience_years)
        self.assertEqual(packet.specification.max_experience_years, 2)
        self.assertEqual(
            packet.specification.requirements[0].value,
            {"min_experience_years": None, "max_experience_years": 2},
        )

    def test_company_filters_are_or_grouped_and_added_to_structured_summary(self):
        packet = _apply_runtime_filters(
            routing_packet(),
            RuntimeFilters(companies=["Acme", "Beta", " acme "]),
        )

        self.assertEqual(packet.structured_requirements["companies"], ["Acme", "Beta"])
        self.assertEqual(
            [item.source_of_truth for item in packet.specification.requirements],
            ["candidate_experience", "candidate_experience"],
        )
        self.assertEqual(
            {item.group_id for item in packet.specification.requirements},
            {"runtime_filter_companies"},
        )
        self.assertEqual(
            {item.relationship for item in packet.specification.requirements},
            {"OR"},
        )

    def test_domain_filters_are_normalized_and_added_as_structured_constraints(self):
        packet = _apply_runtime_filters(
            routing_packet(),
            RuntimeFilters(domains=["technical", "Customer_Success", " TECHNICAL "]),
        )

        self.assertEqual(
            packet.structured_requirements["domains"],
            ["TECHNICAL", "CUSTOMER_SUCCESS"],
        )
        self.assertEqual(len(packet.specification.requirements), 1)
        requirement = packet.specification.requirements[0]
        self.assertEqual(requirement.field, "domains")
        self.assertEqual(requirement.value, ["TECHNICAL", "CUSTOMER_SUCCESS"])
        self.assertEqual(requirement.source_of_truth, "candidate_resume")

    def test_runtime_application_does_not_mutate_the_original_packet(self):
        original = routing_packet(minimum=2, maximum=10)
        _apply_runtime_filters(
            original,
            RuntimeFilters(seniority=["mid"], experience_min=4),
        )

        self.assertEqual(original.specification.min_experience_years, 2)
        self.assertEqual(original.specification.max_experience_years, 10)
        self.assertEqual(original.specification.requirements, [])


class RuntimeDomainRetrievalTests(unittest.TestCase):
    def test_domain_filter_returns_candidates_with_a_matching_resume_classification(self):
        engine = create_engine("sqlite:///:memory:")
        try:
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                technical = Candidate(name="Technical candidate")
                sales = Candidate(name="Sales candidate")
                db.add_all([technical, sales])
                db.flush()
                db.add_all(
                    [
                        Resume(
                            candidate_id=technical.id,
                            filename="technical.pdf",
                            storage_key="technical",
                            file_hash="technical",
                            primary_domain="TECHNICAL",
                        ),
                        Resume(
                            candidate_id=sales.id,
                            filename="sales.pdf",
                            storage_key="sales",
                            file_hash="sales",
                            primary_domain="SALES",
                        ),
                    ]
                )
                db.commit()

                results = retrieve_structured_candidates(
                    db=db,
                    requirements={"domains": ["TECHNICAL"]},
                )

                self.assertEqual(
                    {item["candidate"].name for item in results},
                    {"Technical candidate"},
                )
        finally:
            engine.dispose()


class RuntimeSeniorityScopeRetrievalTests(unittest.TestCase):
    def test_relevant_role_seniority_does_not_use_unrelated_total_experience(self):
        engine = create_engine("sqlite:///:memory:")
        try:
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                developer = Role(title="Software Developer", normalized_title="software developer")
                analyst = Role(title="Business Analyst", normalized_title="business analyst")
                db.add_all([developer, analyst])
                db.flush()
                candidate = Candidate(
                    name="Mostly unrelated experience",
                    total_experience_months=84,
                )
                db.add(candidate)
                db.flush()
                db.add_all(
                    [
                        Experience(
                            candidate_id=candidate.id,
                            role_id=developer.id,
                            start_date=date(2025, 1, 1),
                            end_date=date(2026, 1, 1),
                        ),
                        Experience(
                            candidate_id=candidate.id,
                            role_id=analyst.id,
                            start_date=date(2017, 1, 1),
                            end_date=date(2023, 1, 1),
                        ),
                    ]
                )
                db.commit()

                results = retrieve_structured_candidates(
                    db=db,
                    requirements={
                        "roles": ["developer"],
                        "seniority_filter": {
                            "experience_scope": "RELEVANT_ROLE",
                            "role_titles": ["developer"],
                            "acceptable_min_months": 60,
                            "acceptable_max_months": 144,
                        },
                    },
                )

                self.assertEqual(results, [])
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()

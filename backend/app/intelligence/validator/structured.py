import re
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.candidate import Candidate
from app.database.models.candidate_skill import CandidateSkill
from app.database.models.experience import Experience
from app.database.models.skill import Skill
from app.database.models.experience_skill import ExperienceSkill
from app.database.location_utils import format_candidate_location, location_matches
from app.intelligence.seniority_policy import get_seniority_policy, classify_experience_fit
from app.search.normalization import (
    equivalent_terms,
    role_matches as _role_matches,
)
from app.intelligence.validator.rules import (
    _normalize,
    _tokens,
    _normalize_role_for_match,
    _experience_duration_months,
    _combined_experience_months,
    _experience_source_label,
    _matched_experience_payload,
    _select_best_matching_experience,
    _company_matches,
    _matching_evidence,
    _format_months,
    _experience_requirement_label,
    _supports_negative_technology_evidence,
    _candidate_has_structured_skill,
)

def validate_structured_requirements(
    db: Session,
    candidate_id: int,
    requirements: dict,
    evidence: list[dict],
) -> tuple[bool, list[dict], list[dict], list[dict]]:
    """
    Validate hard structured requirements.

    PostgreSQL is the source of truth for:
    - skills, roles, companies, location, total experience
    """

    candidate = db.scalar(
        select(Candidate).where(
            Candidate.id == candidate_id
        )
    )

    if candidate is None:
        return (
            False,
            [
                {
                    "type": "CANDIDATE",
                    "reason": "Candidate not found",
                }
            ],
            [],
            [],
        )

    failures = []
    matched = []
    matched_evidence = []

    def add_match(
        requirement_type: str,
        requirement: str,
        candidate_value,
        supporting: list[dict] | None = None,
        matched_experience: Experience | None = None,
    ) -> None:
        supporting = supporting or []
        supporting = [
            {**item, "requirement": requirement}
            for item in supporting
        ]
        match = {
            "type": requirement_type,
            "requirement": requirement,
            "matched": True,
            "candidate_value": candidate_value,
            "evidence": supporting,
        }
        if matched_experience is not None:
            match["matched_experience"] = _matched_experience_payload(
                matched_experience
            )
        matched.append(match)
        matched_evidence.extend(supporting)

    requested_location = requirements.get("location")
    if requested_location:
        if not location_matches(requested_location, candidate.location):
            failures.append({
                "type": "LOCATION",
                "required": requested_location,
                "available": format_candidate_location(candidate.location),
            })
        else:
            add_match(
                "location",
                requested_location,
                format_candidate_location(candidate.location),
            )

    # --------------------------------------------------
    # Skills
    # --------------------------------------------------

    requested_skills = (
        requirements.get("skills")
        or []
    )
    skill_alias_groups = requirements.get("skill_aliases") or {}
    requested_roles = requirements.get("roles") or []
    role_experiences = []
    if requested_roles:
        role_experiences = db.scalars(
            select(Experience).where(
                Experience.candidate_id == candidate_id
            )
        ).all()

    if requested_skills:
        if requested_roles:
            matching_role_experience_ids = {
                experience.id
                for experience in role_experiences
                if experience.role
                and experience.role.title
                and any(
                    _role_matches(requested_role, experience.role.title)
                    for requested_role in requested_roles
                )
            }
            experience_skill_rows = db.scalars(
                select(ExperienceSkill)
                .join(Skill, Skill.id == ExperienceSkill.skill_id)
                .where(
                    ExperienceSkill.candidate_id == candidate_id,
                )
            ).all()
            experience_skills = {
                _normalize(row.skill.normalized_name): row
                for row in experience_skill_rows
                if row.skill and row.experience_id in matching_role_experience_ids
            }
            candidate_skills = {}
        else:
            candidate_skill_rows = db.scalars(
                select(CandidateSkill)
                .where(
                    CandidateSkill.candidate_id
                    == candidate_id
                )
            ).all()
            candidate_skills = {
                _normalize(row.skill.normalized_name): row
                for row in candidate_skill_rows
                if row.skill
            }
            experience_skills = {}

        for skill in requested_skills:

            alias_terms = skill_alias_groups.get(skill) or equivalent_terms(skill, "skill") or [skill]
            normalized_aliases = [_normalize(alias) for alias in alias_terms]
            skill_row = next(
                (
                    candidate_skills.get(alias)
                    for alias in normalized_aliases
                    if candidate_skills.get(alias)
                ),
                None,
            )
            experience_skill_row = next(
                (
                    experience_skills.get(alias)
                    for alias in normalized_aliases
                    if experience_skills.get(alias)
                ),
                None,
            )
            matched_skill = experience_skill_row if requested_roles else skill_row
            if matched_skill is None:
                failures.append(
                    {
                        "type": "SKILL",
                        "required": skill,
                        **(
                            {"reason": "Skill is not linked to a matching role experience"}
                            if requested_roles
                            else {}
                        ),
                    }
                )
            else:
                skill_evidence = []
                if requested_roles:
                    experience = next(
                        (
                            item
                            for item in role_experiences
                            if item.id == experience_skill_row.experience_id
                        ),
                        None,
                    )
                    skill_evidence = [
                        {
                            "candidate_id": candidate_id,
                            "evidence_type": "experience",
                            "source_id": experience_skill_row.id,
                            "source_kind": "experience_record",
                            "experience_id": experience_skill_row.experience_id,
                            "text": experience_skill_row.evidence
                            or (experience.description if experience else None),
                            "retrieval_score": 0.0,
                        }
                    ]
                elif skill_row.evidence:
                    skill_evidence.append({
                        "candidate_id": candidate_id,
                        "evidence_type": "skill",
                        "source_id": skill_row.id,
                        "text": skill_row.evidence,
                        "retrieval_score": 0.0,
                    })
                if not skill_evidence and not requested_roles:
                    skill_evidence = _matching_evidence(
                        evidence,
                        skill,
                        preferred_types={"skills", "experience", "project"},
                    )
                add_match("skill", skill, matched_skill.skill.name, skill_evidence)

    # --------------------------------------------------
    # Total experience
    # --------------------------------------------------

    minimum_years = requirements.get(
        "min_experience_years"
    )

    maximum_years = requirements.get(
        "max_experience_years"
    )

    actual_months = int(
        candidate.total_experience_months
        or 0
    )
    minimum_exclusive = bool(requirements.get("min_experience_exclusive"))

    if minimum_years is not None:

        required_months = (
            float(minimum_years)
            * 12
        )

        if actual_months < required_months or (minimum_exclusive and actual_months <= required_months):

            failures.append(
                {
                    "type": "MIN_EXPERIENCE",
                    "required_years": float(
                        minimum_years
                    ),
                    "actual_months": actual_months,
                }
            )

    if maximum_years is not None:

        maximum_months = (
            float(maximum_years)
            * 12
        )

        if actual_months >= maximum_months + 12:

            failures.append(
                {
                    "type": "MAX_EXPERIENCE",
                    "required_years": float(
                        maximum_years
                    ),
                    "actual_months": actual_months,
                }
            )

    minimum_passes = (
        minimum_years is None
        or (actual_months > float(minimum_years) * 12 if minimum_exclusive
            else actual_months >= float(minimum_years) * 12)
    )
    experience_passes = (
        minimum_passes
        and (maximum_years is None or actual_months < (float(maximum_years) + 1) * 12)
    )
    if minimum_years is not None or maximum_years is not None:
        if experience_passes:
            add_match(
                "experience",
                _experience_requirement_label(minimum_years, maximum_years),
                _format_months(actual_months),
            )

    # --------------------------------------------------
    # Seniority
    # --------------------------------------------------

    seniority_filter = requirements.get("seniority_filter")
    if seniority_filter:
        seniority_value = seniority_filter.get("seniority")
        policy = get_seniority_policy(seniority_value)

        if policy is not None:
            experience_scope = seniority_filter.get(
                "experience_scope",
                policy.experience_scope,
            )
            requested_seniority_roles = seniority_filter.get("role_titles") or []

            if experience_scope == "RELEVANT_ROLE" and requested_seniority_roles:
                seniority_experiences = db.scalars(
                    select(Experience).where(
                        Experience.candidate_id == candidate_id
                    )
                ).all()

                matching_experiences = [
                    experience
                    for experience in seniority_experiences
                    if experience.role
                    and experience.role.title
                    and any(
                        _role_matches(requested_role, experience.role.title)
                        for requested_role in requested_seniority_roles
                    )
                ]

                dated_matching_experiences = [
                    experience
                    for experience in matching_experiences
                    if _experience_duration_months(experience) is not None
                ]

                seniority_months = (
                    _combined_experience_months(dated_matching_experiences)
                    if dated_matching_experiences
                    else None
                )
            else:
                experience_scope = "OVERALL"
                seniority_months = (
                    int(candidate.total_experience_months)
                    if candidate.total_experience_months is not None
                    else None
                )

            seniority_fit = (
                classify_experience_fit(seniority_months, policy)
                if seniority_months is not None
                else "OUTSIDE"
            )

            if seniority_fit == "OUTSIDE":
                failures.append({
                    "type": "SENIORITY",
                    "required": policy.seniority,
                    "experience_scope": experience_scope,
                    "actual_months": seniority_months,
                    "acceptable_min_months": policy.acceptable_min_months,
                    "acceptable_max_months": policy.acceptable_max_months,
                    "reason": (
                        "Experience could not be established from dated records"
                        if seniority_months is None
                        else "Candidate experience is outside the acceptable seniority range"
                    ),
                })
            else:
                matched.append({
                    "type": "seniority",
                    "requirement": policy.seniority,
                    "matched": True,
                    "candidate_value": _format_months(seniority_months),
                    "seniority": policy.seniority,
                    "seniority_fit": seniority_fit,
                    "experience_months": seniority_months,
                    "experience_scope": experience_scope,
                    "preferred_min_months": policy.preferred_min_months,
                    "preferred_max_months": policy.preferred_max_months,
                    "acceptable_min_months": policy.acceptable_min_months,
                    "acceptable_max_months": policy.acceptable_max_months,
                    "evidence": [],
                })

    # --------------------------------------------------
    # Roles
    # --------------------------------------------------

    requested_roles = (
        requirements.get("roles")
        or []
    )

    if requested_roles:
        for role in requested_roles:
            matched_experience = _select_best_matching_experience(
                role,
                role_experiences,
            )
            if not matched_experience:
                failures.append(
                    {
                        "type": "ROLE",
                        "required": role,
                        "available": [
                            experience.role.title for experience in role_experiences
                            if experience.role and experience.role.title
                        ],
                    }
                )
            else:
                role_evidence = ([{
                    "candidate_id": candidate_id,
                    "evidence_type": "experience",
                    "source_id": matched_experience.id,
                    "source_kind": "experience_record",
                    "experience_id": matched_experience.id,
                    "text": matched_experience.description,
                    "retrieval_score": 0.0,
                }] if matched_experience.description else [])
                add_match(
                    "role",
                    role,
                    matched_experience.role.title,
                    role_evidence,
                    matched_experience=matched_experience,
                )

    # --------------------------------------------------
    # Companies
    # --------------------------------------------------

    requested_companies = (
        requirements.get("companies")
        or []
    )

    if requested_companies:
        company_aliases = requirements.get("company_aliases") or {}

        experiences = db.scalars(
            select(Experience)
            .where(
                Experience.candidate_id
                == candidate_id
            )
        ).all()

        for company in requested_companies:
            matched_company = next(
                (
                    experience for experience in experiences
                    if experience.company and experience.company.name
                    and _company_matches(
                        company,
                        experience.company.name,
                        company_aliases.get(company),
                    )
                ),
                None,
            )
            if not matched_company:
                failures.append(
                    {
                        "type": "COMPANY",
                        "required": company,
                        "available": [
                            experience.company.name for experience in experiences
                            if experience.company and experience.company.name
                        ],
                    }
                )
            else:
                company_evidence = ([{
                    "candidate_id": candidate_id,
                    "evidence_type": "experience",
                    "source_id": matched_company.id,
                    "source_kind": "experience_record",
                    "experience_id": matched_company.id,
                    "text": matched_company.description,
                    "retrieval_score": 0.0,
                }] if matched_company.description else [])
                add_match(
                    "company",
                    company,
                    matched_company.company.name,
                    company_evidence,
                    matched_experience=matched_company,
                )

    return (
        len(failures) == 0,
        failures,
        matched,
        matched_evidence,
    )


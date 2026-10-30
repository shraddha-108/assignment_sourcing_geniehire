from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.candidate import Candidate
from app.database.models.candidate_evidence import CandidateEvidence
from app.database.models.candidate_skill import CandidateSkill
from app.database.models.company import Company
from app.database.models.education import Education
from app.database.models.experience import Experience
from app.database.models.experience_skill import ExperienceSkill
from app.database.models.project import Project
from app.database.models.project_skill import ProjectSkill
from app.database.models.resume import Resume
from app.database.models.resume_section import ResumeSection
from app.database.models.role import Role
from app.database.models.skill import Skill
from app.database.models.location import Location
from app.ingestion.skill_taxonomy import get_skill_metadata
from app.ingestion.schemas.resume import ResumeData


# ============================================================
# Generic normalization
# ============================================================

def normalize_name(value: str) -> str:
    return " ".join(
        value.lower().strip().split()
    )


# ============================================================
# Company
# ============================================================

def get_or_create_company(
    db: Session,
    name: str,
) -> Company:

    normalized = normalize_name(name)

    company = db.scalar(
        select(Company).where(
            Company.normalized_name == normalized
        )
    )

    if company:
        return company

    company = Company(
        name=name.strip(),
        normalized_name=normalized,
    )

    db.add(company)
    db.flush()

    return company


# ============================================================
# Role
# ============================================================

def get_or_create_role(
    db: Session,
    title: str,
) -> Role:

    normalized = normalize_name(title)

    role = db.scalar(
        select(Role).where(
            Role.normalized_title == normalized
        )
    )

    if role:
        return role

    role = Role(
        title=title.strip(),
        normalized_title=normalized,
    )

    db.add(role)
    db.flush()

    return role


# ============================================================
# Skill
# ============================================================

def get_or_create_skill(
    db: Session,
    name: str,
) -> Skill:

    if not name or not name.strip():
        raise ValueError("Skill name cannot be empty.")

    canonical_name, skill_type, description = (
        get_skill_metadata(name)
    )

    normalized = normalize_name(canonical_name)

    skill = db.scalar(
        select(Skill).where(
            Skill.normalized_name == normalized
        )
    )

    if skill:
        # Enrich existing skill if metadata is currently missing.
        if skill_type and not skill.skill_type:
            skill.skill_type = skill_type

        if description and not skill.description:
            skill.description = description

        if skill_type or description:
            db.flush()

        return skill

    skill = Skill(
        name=canonical_name,
        normalized_name=normalized,
        skill_type=skill_type,
        description=description,
    )

    db.add(skill)
    db.flush()

    return skill


# ============================================================
# Location helpers
# ============================================================

COUNTRY_NAMES = {
    "india",
    "bharat",
    "usa",
    "united states",
    "uk",
    "united kingdom",
    "canada",
    "australia",
    "singapore",
}


INDIAN_STATES = {
    "andhra pradesh",
    "arunachal pradesh",
    "assam",
    "bihar",
    "chhattisgarh",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
    "delhi",
}


# Known city aliases that are useful for recruiter location search.
CITY_ALIASES = {
    "pcmc": "Pimpri-Chinchwad",
    "pimpri chinchwad": "Pimpri-Chinchwad",
    "pimpri-chinchwad": "Pimpri-Chinchwad",
}


# Known city -> state mappings.
# Keep this list conservative. We only infer a state when
# the mapping is unambiguous.
CITY_STATE_MAP = {
    "pune": "Maharashtra",
    "pimpri-chinchwad": "Maharashtra",
    "mumbai": "Maharashtra",
    "nagpur": "Maharashtra",
    "nashik": "Maharashtra",
    "aurangabad": "Maharashtra",
    "chhatrapati sambhajinagar": "Maharashtra",
    "kolhapur": "Maharashtra",
    "solapur": "Maharashtra",
    "thane": "Maharashtra",
    "bengaluru": "Karnataka",
    "bangalore": "Karnataka",
    "hyderabad": "Telangana",
    "chennai": "Tamil Nadu",
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "ahmedabad": "Gujarat",
    "jaipur": "Rajasthan",
    "lucknow": "Uttar Pradesh",
    "noida": "Uttar Pradesh",
    "gurugram": "Haryana",
    "gurgaon": "Haryana",
}


def clean_location_value(value: str) -> str:
    """
    Clean common separators and whitespace before parsing.

    Examples:
        Pune-Maharashtra
        Pune - Maharashtra
        Pune, Maharashtra
    """

    value = " ".join(
        value.strip().split()
    )

    return value


def normalize_location_parts(
    value: str,
) -> tuple[str, str | None, str | None]:
    """
    Convert the parser's raw location string into:

        city
        state
        country

    This function is intentionally conservative.

    The parser extracts a raw location string from the resume.
    This function converts that raw string into the structured
    fields required by the Location table.
    """

    value = clean_location_value(value)

    if not value:
        raise ValueError(
            "Candidate location cannot be empty."
        )

    # --------------------------------------------------------
    # Normalize common separators
    # --------------------------------------------------------

    lowered = value.casefold()

    # Example:
    # "Pune-Maharashtra"
    # "Pune - Maharashtra"
    #
    # Convert only when the second portion is a known
    # Indian state.
    if "-" in value:
        hyphen_parts = [
            part.strip()
            for part in value.split("-")
            if part.strip()
        ]

        if len(hyphen_parts) == 2:
            left = normalize_name(
                hyphen_parts[0]
            )
            right = normalize_name(
                hyphen_parts[1]
            )

            if right in INDIAN_STATES:
                value = (
                    f"{hyphen_parts[0]}, "
                    f"{hyphen_parts[1]}"
                )

    # --------------------------------------------------------
    # Handle "At Post ... , Ta. Dist. ..."
    # --------------------------------------------------------

    # Example:
    # "At Post Kanshivani, Ta. Dist. Akola"
    #
    # "Ta. Dist. Akola" is NOT a state.
    # Akola is a district in Maharashtra.
    #
    # Since the current Location table has no district field,
    # we preserve the locality as city and infer Maharashtra
    # from the known Akola district reference.

    lowered = value.casefold()

    if (
        "at post" in lowered
        and "ta. dist." in lowered
    ):
        parts = [
            part.strip()
            for part in value.split(",")
            if part.strip()
        ]

        city_part = parts[0]

        city_part = city_part.replace(
            "At Post",
            "",
        ).replace(
            "at post",
            "",
        ).strip()

        if city_part:
            city = city_part

            if "akola" in lowered:
                return (
                    city,
                    "Maharashtra",
                    "India",
                )

    # --------------------------------------------------------
    # Standard comma-separated parsing
    # --------------------------------------------------------

    parts = [
        part.strip()
        for part in value.split(",")
        if part.strip()
    ]

    if not parts:
        raise ValueError(
            "Candidate location cannot be empty."
        )

    city = parts[0]
    state = None
    country = None

    # --------------------------------------------------------
    # Detect country
    # --------------------------------------------------------

    if (
        len(parts) > 1
        and parts[-1].casefold() in COUNTRY_NAMES
    ):
        country = parts[-1]
        parts_without_country = parts[:-1]
    else:
        parts_without_country = parts

    # --------------------------------------------------------
    # Detect state
    # --------------------------------------------------------

    if len(parts_without_country) >= 2:

        possible_state = parts_without_country[-1]

        if (
            possible_state.casefold()
            in INDIAN_STATES
        ):
            state = possible_state

        elif (
            len(parts_without_country) == 2
        ):
            # Preserve existing generic behaviour for
            # non-India locations such as:
            #
            # "Toronto, Ontario"
            #
            # but don't treat obvious district/admin
            # strings as states.
            possible_state_lower = (
                possible_state.casefold()
            )

            if not (
                possible_state_lower.startswith(
                    "ta. dist."
                )
                or possible_state_lower.startswith(
                    "dist."
                )
                or possible_state_lower.startswith(
                    "district"
                )
            ):
                state = possible_state

    # --------------------------------------------------------
    # Normalize city aliases
    # --------------------------------------------------------

    city_normalized = normalize_name(city)

    canonical_city = CITY_ALIASES.get(
        city_normalized,
        city,
    )

    # --------------------------------------------------------
    # Infer state from known city
    # --------------------------------------------------------

    canonical_city_normalized = normalize_name(
        canonical_city
    )

    if state is None:
        inferred_state = CITY_STATE_MAP.get(
            canonical_city_normalized
        )

        if inferred_state:
            state = inferred_state

    # --------------------------------------------------------
    # Infer India for known Indian locations
    # --------------------------------------------------------

    if (
        country is None
        and state is not None
        and normalize_name(state) in {
            normalize_name(item)
            for item in INDIAN_STATES
        }
    ):
        country = "India"

    # If the input explicitly says India/Bharat,
    # preserve that.
    if country:
        country_normalized = country.casefold()

        if country_normalized == "bharat":
            country = "India"

    return (
        canonical_city,
        state,
        country,
    )


def get_or_create_location(
    db: Session,
    value: str,
) -> Location:

    city, state, country = normalize_location_parts(
        value
    )

    normalized_city = normalize_name(city)

    normalized_state = (
        normalize_name(state)
        if state
        else None
    )

    normalized_country = (
        normalize_name(country)
        if country
        else None
    )

    # --------------------------------------------------------
    # Check existing normalized location
    # --------------------------------------------------------

    location = db.scalar(
        select(Location).where(
            Location.normalized_city
            == normalized_city,
            Location.normalized_state
            == normalized_state,
            Location.normalized_country
            == normalized_country,
        )
    )

    if location:
        return location

    # --------------------------------------------------------
    # Create new location
    # --------------------------------------------------------

    location = Location(
        city=city,
        state=state,
        country=country,
        normalized_city=normalized_city,
        normalized_state=normalized_state,
        normalized_country=normalized_country,
    )

    db.add(location)
    db.flush()

    return location


# ============================================================
# Resume section
# ============================================================

def create_section(
    db: Session,
    resume_id: int,
    section_type: str,
    title: str | None,
    content: str,
    section_order: int,
) -> ResumeSection:

    section = ResumeSection(
        resume_id=resume_id,
        section_type=section_type,
        title=title,
        content=content,
        section_order=section_order,
    )

    db.add(section)
    db.flush()

    return section


# ============================================================
# Candidate evidence
# ============================================================

def create_evidence(
    db: Session,
    candidate_id: int,
    resume_id: int,
    section_id: int,
    evidence_type: str,
    text: str,
) -> CandidateEvidence:

    evidence = CandidateEvidence(
        candidate_id=candidate_id,
        resume_id=resume_id,
        resume_section_id=section_id,
        evidence_type=evidence_type,
        text=text,
    )

    db.add(evidence)
    db.flush()

    return evidence


# ============================================================
# Persist candidate
# ============================================================

def persist_candidate(
    db: Session,
    resume_data: ResumeData,
    filename: str,
    storage_key: str,
    file_hash: str,
    file_type: str | None = None,
    file_size: int | None = None,
) -> Candidate:

    candidate_data = resume_data.candidate

    # ==================================================
    # 1. Candidate
    # ==================================================

    location = (
        get_or_create_location(
            db,
            candidate_data.location,
        )
        if candidate_data.location
        else None
    )

    candidate = Candidate(
        name=candidate_data.name,
        email=candidate_data.email,
        phone=candidate_data.phone,
        headline=candidate_data.headline,
        summary=candidate_data.summary,
        location_id=(
            location.id
            if location
            else None
        ),
        linkedin_url=candidate_data.linkedin_url,
        github_url=candidate_data.github_url,
        portfolio_url=candidate_data.portfolio_url,
    )

    db.add(candidate)
    db.flush()

    # ==================================================
    # 2. Resume
    # ==================================================

    resume = Resume(
        candidate_id=candidate.id,
        filename=filename,
        storage_key=storage_key,
        file_hash=file_hash,
        file_type=file_type,
        file_size=file_size,
    )

    db.add(resume)
    db.flush()

    # ==================================================
    # 3. Candidate Skills
    # ==================================================

    for skill_data in resume_data.skills:

        if not skill_data.name:
            continue

        skill = get_or_create_skill(
            db,
            skill_data.name,
        )

        candidate_skill = CandidateSkill(
            candidate_id=candidate.id,
            skill_id=skill.id,
        )

        db.add(candidate_skill)

    # ==================================================
    # 4. Experiences
    # ==================================================

    for experience_data in resume_data.experiences:

        company = None
        role = None

        # ----------------------------------------------
        # Company
        # ----------------------------------------------

        if experience_data.company:

            company = get_or_create_company(
                db,
                experience_data.company,
            )

        # ----------------------------------------------
        # Role
        # ----------------------------------------------

        if experience_data.title:

            role = get_or_create_role(
                db,
                experience_data.title,
            )

        # ----------------------------------------------
        # Experience
        # ----------------------------------------------

        experience = Experience(
            candidate_id=candidate.id,

            company_id=(
                company.id
                if company
                else None
            ),

            role_id=(
                role.id
                if role
                else None
            ),

            start_date=experience_data.start_date,
            end_date=experience_data.end_date,

            is_current=(
                experience_data.end_date is None
            ),

            duration_months=(
                experience_data.duration_months
            ),

            description=(
                experience_data.evidence
            ),
        )

        db.add(experience)
        db.flush()

        # ----------------------------------------------
        # Experience → Skills
        # ----------------------------------------------

        for skill_name in experience_data.skills:

            if not skill_name:
                continue

            skill = get_or_create_skill(
                db,
                skill_name,
            )

            experience_skill = ExperienceSkill(
                candidate_id=candidate.id,
                experience_id=experience.id,
                skill_id=skill.id,

                first_used_date=(
                    experience_data.start_date
                ),

                last_used_date=(
                    experience_data.end_date
                ),

                months_used=(
                    experience_data.duration_months
                ),

                evidence=(
                    experience_data.evidence
                ),
            )

            db.add(experience_skill)

        # ----------------------------------------------
        # Current company / role
        # ----------------------------------------------

        if experience_data.end_date is None:

            if company:
                candidate.current_company_id = (
                    company.id
                )

            if role:
                candidate.current_role_id = (
                    role.id
                )

    # ==================================================
    # 5. Projects
    # ==================================================

    for project_data in resume_data.projects:

        project = Project(
            candidate_id=candidate.id,
            title=project_data.title,
            description=project_data.description,
        )

        db.add(project)
        db.flush()

        # ----------------------------------------------
        # Project → Skills
        # ----------------------------------------------

        for skill_name in project_data.skills:

            if not skill_name:
                continue

            skill = get_or_create_skill(
                db,
                skill_name,
            )

            project_skill = ProjectSkill(
                project_id=project.id,
                skill_id=skill.id,
            )

            db.add(project_skill)

    # ==================================================
    # 6. Education
    # ==================================================

    for education_data in resume_data.education:

        education = Education(
            candidate_id=candidate.id,

            institution=(
                education_data.institution
            ),

            degree=(
                education_data.degree
            ),

            field_of_study=(
                education_data.field_of_study
            ),

            start_date=(
                education_data.start_date
            ),

            end_date=(
                education_data.end_date
            ),
        )

        db.add(education)

    # ==================================================
    # 7. Resume Sections + Candidate Evidence
    # ==================================================

    section_order = 0

    # ----------------------------------------------
    # Summary
    # ----------------------------------------------

    if candidate_data.summary:

        summary_section = create_section(
            db=db,
            resume_id=resume.id,
            section_type="summary",
            title="Summary",
            content=candidate_data.summary,
            section_order=section_order,
        )

        section_order += 1

        create_evidence(
            db=db,
            candidate_id=candidate.id,
            resume_id=resume.id,
            section_id=summary_section.id,
            evidence_type="summary",
            text=candidate_data.summary,
        )

    # ----------------------------------------------
    # Experiences
    # ----------------------------------------------

    for experience_data in resume_data.experiences:

        evidence_text = (
            experience_data.evidence.strip()
        )

        if not evidence_text:
            continue

        experience_section = create_section(
            db=db,
            resume_id=resume.id,
            section_type="experience",
            title=experience_data.title,
            content=evidence_text,
            section_order=section_order,
        )

        section_order += 1

        create_evidence(
            db=db,
            candidate_id=candidate.id,
            resume_id=resume.id,
            section_id=experience_section.id,
            evidence_type="experience",
            text=evidence_text,
        )

    # ----------------------------------------------
    # Projects
    # ----------------------------------------------

    for project_data in resume_data.projects:

        evidence_parts = []

        # Project title
        if project_data.title:
            evidence_parts.append(
                project_data.title.strip()
            )

        # Project description
        if project_data.description:
            evidence_parts.append(
                project_data.description.strip()
            )

        # Project skills
        if project_data.skills:

            skills_text = ", ".join(
                skill.strip()
                for skill in project_data.skills
                if skill and skill.strip()
            )

            if skills_text:
                evidence_parts.append(
                    skills_text
                )

        # Original project evidence
        if project_data.evidence:

            original_evidence = (
                project_data.evidence.strip()
            )

            if original_evidence:
                evidence_parts.append(
                    original_evidence
                )

        # Remove duplicate pieces while preserving order
        unique_parts = []

        for part in evidence_parts:

            if not part:
                continue

            if part not in unique_parts:
                unique_parts.append(part)

        evidence_text = "\n".join(
            unique_parts
        ).strip()

        if not evidence_text:
            continue

        project_section = create_section(
            db=db,
            resume_id=resume.id,
            section_type="project",
            title=project_data.title,
            content=evidence_text,
            section_order=section_order,
        )

        section_order += 1

        create_evidence(
            db=db,
            candidate_id=candidate.id,
            resume_id=resume.id,
            section_id=project_section.id,
            evidence_type="project",
            text=evidence_text,
        )

    # ----------------------------------------------
    # Skills
    # ----------------------------------------------

    if resume_data.skills:

        skill_text = ", ".join(
            skill.name
            for skill in resume_data.skills
            if skill.name
        )

        if skill_text:

            skills_section = create_section(
                db=db,
                resume_id=resume.id,
                section_type="skills",
                title="Skills",
                content=skill_text,
                section_order=section_order,
            )

            section_order += 1

            create_evidence(
                db=db,
                candidate_id=candidate.id,
                resume_id=resume.id,
                section_id=skills_section.id,
                evidence_type="skills",
                text=skill_text,
            )

    # ----------------------------------------------
    # Education
    # ----------------------------------------------

    for education_data in resume_data.education:

        education_parts = [
            value
            for value in [
                education_data.institution,
                education_data.degree,
                education_data.field_of_study,
            ]
            if value
        ]

        education_text = " | ".join(
            education_parts
        )

        if not education_text:
            continue

        education_section = create_section(
            db=db,
            resume_id=resume.id,
            section_type="education",
            title=education_data.degree,
            content=education_text,
            section_order=section_order,
        )

        section_order += 1

        create_evidence(
            db=db,
            candidate_id=candidate.id,
            resume_id=resume.id,
            section_id=education_section.id,
            evidence_type="education",
            text=education_text,
        )

    # ==================================================
    # 8. Total Experience
    # ==================================================

    candidate.total_experience_months = (
        resume_data.total_experience_months
    )

    # ==================================================
    # 9. Commit
    # ==================================================

    db.commit()

    db.refresh(candidate)

    return candidate
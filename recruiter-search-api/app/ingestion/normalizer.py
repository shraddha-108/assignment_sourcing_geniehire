from datetime import date

from app.ingestion.schemas.resume import ResumeData
from app.ingestion.schemas.skill import SkillData


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = " ".join(value.split())

    return value if value else None


def normalize_skill(skill: str) -> str:
    return " ".join(
        skill.lower().strip().split()
    )


def normalize_skills(skills: list[str]) -> list[str]:
    normalized = []
    seen = set()

    for skill in skills:
        value = normalize_skill(skill)

        if value and value not in seen:
            normalized.append(value)
            seen.add(value)

    return normalized


def calculate_months(
    start_date: date,
    end_date: date,
) -> int:
    """
    Calculate experience duration in complete months.
    """

    if end_date < start_date:
        return 0

    return max(
        0,
        (
            (end_date.year - start_date.year) * 12
            + (end_date.month - start_date.month)
        ),
    )


def calculate_total_experience_months(
    resume: ResumeData,
) -> int:
    """
    Calculate total professional experience while
    avoiding double-counting overlapping jobs.
    """

    intervals: list[tuple[date, date]] = []

    today = date.today()

    for experience in resume.experiences:

        if not experience.start_date:
            continue

        start = experience.start_date

        # Current job
        end = experience.end_date or today

        if end < start:
            continue

        intervals.append(
            (start, end)
        )

    if not intervals:
        return 0

    # Sort by start date
    intervals.sort(
        key=lambda interval: interval[0]
    )

    merged: list[list[date]] = []

    current_start, current_end = intervals[0]

    for start, end in intervals[1:]:

        # Overlapping or touching employment periods
        if start <= current_end:

            if end > current_end:
                current_end = end

        else:
            merged.append(
                [current_start, current_end]
            )

            current_start = start
            current_end = end

    merged.append(
        [current_start, current_end]
    )

    total_months = 0

    for start, end in merged:

        total_months += calculate_months(
            start,
            end,
        )

    return total_months


def normalize_resume(
    resume: ResumeData,
) -> ResumeData:

    # ==================================================
    # Candidate
    # ==================================================

    resume.candidate.name = normalize_text(
        resume.candidate.name
    )

    resume.candidate.email = normalize_text(
        resume.candidate.email
    )

    resume.candidate.phone = normalize_text(
        resume.candidate.phone
    )

    resume.candidate.headline = normalize_text(
        resume.candidate.headline
    )

    resume.candidate.summary = normalize_text(
        resume.candidate.summary
    )

    resume.candidate.linkedin_url = normalize_text(
        resume.candidate.linkedin_url
    )

    resume.candidate.github_url = normalize_text(
        resume.candidate.github_url
    )

    resume.candidate.portfolio_url = normalize_text(
        resume.candidate.portfolio_url
    )

    # ==================================================
    # Experiences
    # ==================================================

    for experience in resume.experiences:

        experience.company = normalize_text(
            experience.company
        )

        experience.title = normalize_text(
            experience.title
        )

        experience.skills = normalize_skills(
            experience.skills
        )

        experience.evidence = (
            experience.evidence.strip()
        )

    # ==================================================
    # Candidate-level skills
    # ==================================================

    unique_skills = normalize_skills(
        [
            skill.name
            for skill in resume.skills
            if skill.name
        ]
    )

    resume.skills = [
        SkillData(name=name)
        for name in unique_skills
    ]

    # ==================================================
    # Projects
    # ==================================================

    for project in resume.projects:

        project.title = (
            normalize_text(
                project.title
            )
            or ""
        )

        project.description = (
            normalize_text(
                project.description
            )
            or ""
        )

        project.skills = normalize_skills(
            project.skills
        )

        project.evidence = (
            project.evidence.strip()
        )

    # ==================================================
    # Education
    # ==================================================

    for education in resume.education:

        education.institution = normalize_text(
            education.institution
        )

        education.degree = normalize_text(
            education.degree
        )

        education.field_of_study = normalize_text(
            education.field_of_study
        )

    # ==================================================
    # Calculate individual experience duration
    # ==================================================

    today = date.today()

    for experience in resume.experiences:

        if not experience.start_date:
            continue

        end_date = (
            experience.end_date
            or today
        )

        experience.duration_months = (
            calculate_months(
                experience.start_date,
                end_date,
            )
        )

    # ==================================================
    # Calculate total experience
    # ==================================================

    resume.total_experience_months = (
        calculate_total_experience_months(
            resume
        )
    )

    return resume

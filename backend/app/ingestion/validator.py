from app.ingestion.schemas.resume import ResumeData


def validate_resume(resume: ResumeData) -> None:
    """
    Validate normalized resume data before persistence.

    The validator works only with the canonical ResumeData schema.
    It does not depend on resume section names such as:
    Skills, Professional Skills, Technical Skills, etc.
    """

    errors: list[str] = []

    # ==================================================
    # Candidate
    # ==================================================

    if not resume.candidate.name:
        errors.append(
            "Candidate name is missing."
        )

    # ==================================================
    # Experiences
    # ==================================================

    for index, experience in enumerate(
        resume.experiences
    ):
        prefix = f"Experience {index + 1}"

        # Date validation
        if (
            experience.start_date
            and experience.end_date
            and experience.end_date < experience.start_date
        ):
            errors.append(
                f"{prefix}: end_date is before start_date."
            )

        # Duration validation
        if experience.duration_months < 0:
            errors.append(
                f"{prefix}: duration_months cannot be negative."
            )

        # Company/title are allowed to be missing.
        # We do NOT reject an experience just because
        # one of these fields is unavailable.

        # Skills must be strings
        for skill_index, skill in enumerate(
            experience.skills
        ):
            if not isinstance(skill, str):
                errors.append(
                    f"{prefix}: skill {skill_index + 1} "
                    f"must be a string."
                )

    # ==================================================
    # Candidate-level skills
    # ==================================================

    skill_names: list[str] = []

    for index, skill in enumerate(
        resume.skills
    ):
        if not skill.name:
            errors.append(
                f"Candidate skill {index + 1}: "
                f"skill name is missing."
            )
            continue

        if not isinstance(skill.name, str):
            errors.append(
                f"Candidate skill {index + 1}: "
                f"skill name must be a string."
            )
            continue

        skill_names.append(
            skill.name.strip().lower()
        )

    # Detect duplicate candidate skills
    if len(skill_names) != len(set(skill_names)):
        errors.append(
            "Duplicate candidate skills found."
        )

    # ==================================================
    # Projects
    # ==================================================

    for index, project in enumerate(
        resume.projects
    ):
        prefix = f"Project {index + 1}"

        # Project title is useful for identifying
        # the project, so require it.
        if not project.title:
            errors.append(
                f"{prefix}: project title is missing."
            )

        # Project description can legitimately be empty.
        # We do not reject the project for that.

        # Validate project skills
        for skill_index, skill in enumerate(
            project.skills
        ):
            if not isinstance(skill, str):
                errors.append(
                    f"{prefix}: skill {skill_index + 1} "
                    f"must be a string."
                )

    # ==================================================
    # Education
    # ==================================================

    for index, education in enumerate(
        resume.education
    ):
        prefix = f"Education {index + 1}"

        # Validate education dates
        if (
            education.start_date
            and education.end_date
            and education.end_date < education.start_date
        ):
            errors.append(
                f"{prefix}: end_date is before start_date."
            )

    # ==================================================
    # Total experience
    # ==================================================

    if resume.total_experience_months < 0:
        errors.append(
            "Total experience cannot be negative."
        )

    # ==================================================
    # Final validation result
    # ==================================================

    if errors:
        raise ValueError(
            "Resume validation failed:\n"
            + "\n".join(
                f"- {error}"
                for error in errors
            )
        )
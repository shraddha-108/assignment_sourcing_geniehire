from datetime import date


def recency_score(
    last_used_date: date | None,
    recency_months: int | None,
) -> float:

    if recency_months is None:
        return 100.0

    if last_used_date is None:
        return 0.0

    cutoff_date = date.today().replace(
        day=1,
    )

    months_difference = (
        (cutoff_date.year - last_used_date.year) * 12
        + cutoff_date.month
        - last_used_date.month
    )

    if months_difference <= 0:
        return 100.0

    if months_difference >= recency_months:
        return 0.0

    return round(
        100 * (
            1
            - months_difference / recency_months
        ),
        2,
    )


def experience_score(
    total_months: int | None,
    minimum_years: float | None,
) -> float:

    # If the recruiter did not specify an
    # experience requirement, experience should
    # not affect the score.
    if minimum_years is None:
        return 100.0

    # If experience is required but the candidate's
    # experience data is unavailable, the candidate
    # cannot receive experience credit.
    if total_months is None:
        return 0.0

    required_months = minimum_years * 12

    if required_months <= 0:
        return 100.0

    if total_months >= required_months:
        return 100.0

    return round(
        (total_months / required_months) * 100,
        2,
    )


def skill_score(
    last_used_date: date | None,
    total_months: int | None,
    recency_months: int | None,
    minimum_years: float | None,
) -> float:

    recency = recency_score(
        last_used_date,
        recency_months,
    )

    experience = experience_score(
        total_months,
        minimum_years,
    )

    return round(
        (recency * 0.6)
        + (experience * 0.4),
        2,
    )


def score_candidates(
    candidates: list[dict],
    requirements: dict,
) -> list[dict]:

    scored = []

    recency_scope = requirements.get(
        "recency_scope"
    )

    # Recency should only be applied to the
    # structured skill when the recruiter means
    # recent use of that skill.
    #
    # Example:
    # "Python developers with recent Python experience"
    # -> SKILL
    #
    # "Python developers who recently worked on
    # machine learning projects"
    # -> SEMANTIC
    #
    # In the second case, Python's last_used_date
    # must NOT be used to prove recent ML work.
    structured_recency_months = None

    if (
        recency_scope is None
        or recency_scope == "SKILL"
    ):
        structured_recency_months = (
            requirements.get(
                "recency_months"
            )
        )

    for candidate in candidates:

        score = skill_score(
            last_used_date=(
                candidate.get("last_used_date")
            ),
            total_months=(
                candidate.get("total_months")
            ),
            recency_months=(
                structured_recency_months
            ),
            minimum_years=(
                requirements.get(
                    "experience_min_years"
                )
            ),
        )

        item = dict(candidate)

        item["score"] = score

        scored.append(item)

    return scored
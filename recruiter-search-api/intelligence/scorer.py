from datetime import date


def recency_score(last_used_date):
    if not last_used_date:
        return 0

    days_since_used = (
        date.today() - last_used_date
    ).days

    score = 100 - (
        days_since_used / (5 * 365)
    ) * 100

    return max(0, min(100, score))


def experience_score(total_months):
    score = (
        total_months / 60
    ) * 100

    return max(0, min(100, score))


def skill_score(
    last_used_date,
    total_months,
):
    recency = recency_score(
        last_used_date
    )

    experience = experience_score(
        total_months
    )

    return (
        recency * 0.60
        + experience * 0.40
    )


def score_candidates(
    candidates: list[dict],
) -> list[dict]:

    scored = []

    for item in candidates:

        score = skill_score(
            item["last_used_date"],
            item["total_months"],
        )

        scored.append(
            {
                **item,
                "score": round(score, 2),
            }
        )

    return scored
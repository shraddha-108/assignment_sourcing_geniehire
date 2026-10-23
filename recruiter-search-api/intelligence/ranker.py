def rank_candidates(
    candidates: list[dict],
    requested_count: int,
    count_explicit: bool,
) -> list[dict]:

    candidates.sort(
        key=lambda candidate: candidate["score"],
        reverse=True,
    )

    if count_explicit:
        return candidates[:requested_count]

    return candidates
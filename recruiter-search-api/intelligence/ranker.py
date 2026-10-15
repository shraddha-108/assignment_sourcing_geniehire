def rank_candidates(
    candidates: list[dict],
    requested_count: int,
) -> list[dict]:

    candidates.sort(
        key=lambda candidate: candidate["score"],
        reverse=True,
    )

    return candidates[:requested_count]
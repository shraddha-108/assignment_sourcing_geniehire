def rank_candidates(
    candidates: list[dict],
    requested_count: int,
) -> list[dict]:
    """
    Sort validated candidates by final score
    and return the requested number.
    """

    eligible = []
    for item in candidates:
        validation = item.get("validation") or {}
        status = item.get("match_status") or validation.get("match_status")
        if status == "NO_MATCH" or validation.get("valid") is False:
            continue
        eligible.append(item)

    def status_for(item: dict) -> str:
        validation = item.get("validation") or {}
        return item.get("match_status") or validation.get("match_status") or "MATCH"

    candidates = sorted(
        eligible,
        key=lambda item: (
            0 if status_for(item) == "MATCH" else 1,
            -float(item.get("score", 0.0)),
        ),
    )

    # A person can have duplicate candidate rows from repeated resume
    # ingestion. Keep only their highest-ranked profile in search results.
    deduplicated = []
    seen_people = set()

    for item in candidates:
        candidate = item.get("candidate")
        email = getattr(candidate, "email", None)
        linkedin_url = getattr(candidate, "linkedin_url", None)

        if email and email.strip():
            person_key = ("email", email.strip().casefold())
        elif linkedin_url and linkedin_url.strip():
            person_key = ("linkedin", linkedin_url.strip().rstrip("/").casefold())
        else:
            person_key = ("candidate_id", item.get("candidate_id"))

        if person_key in seen_people:
            continue

        seen_people.add(person_key)
        deduplicated.append(item)

    return deduplicated[
        :requested_count
    ]

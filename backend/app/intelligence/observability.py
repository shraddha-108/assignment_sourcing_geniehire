"""Small helpers for structured, requirement-addressable search traces."""


def rejection_records(candidate_id: int, stage: str, failures: list[dict]) -> list[dict]:
    return [
        {
            "candidate_id": candidate_id,
            "requirement_id": failure.get("requirement_id"),
            "stage": stage,
            "reason": failure.get("reason") or failure.get("type"),
            "details": failure,
        }
        for failure in failures
    ]

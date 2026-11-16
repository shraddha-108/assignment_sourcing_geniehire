from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.intelligence.validator.rules import (
    _normalize_for_source,
    _resolve_experience_source,
)

def validate_temporal_requirements(
    db: Session,
    candidate_id: int,
    requirements: list,
    evidence: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Validate time only against the dated source for its dependency evidence."""
    by_id = {item.id: item for item in requirements}
    failures = []
    matches = []
    today = date.today()
    for requirement in requirements:
        if requirement.type != "TEMPORAL":
            continue
        dependency_evidence = []
        for dependency_id in requirement.dependencies:
            dependency = by_id.get(dependency_id)
            if dependency is None:
                continue
            expected_text = _normalize_for_source(
                str(dependency.value or dependency.normalized_text)
            )
            dependency_evidence.extend(
                item for item in evidence
                if _normalize_for_source(item.get("requirement")) == expected_text
            )
        if not dependency_evidence:
            # The activity itself did not qualify, so its date cannot be
            # evaluated. Keep this as a dependent non-match instead of adding
            # a second, misleading hard failure for missing dates.
            matches.append({
                "type": "temporal", "requirement_id": requirement.id,
                "requirement": requirement.original_text, "matched": False,
                "reason": "No supporting activity evidence to date",
                "evidence": [],
            })
            continue
        sources = [
            _resolve_experience_source(db, candidate_id, item)
            for item in dependency_evidence
        ]
        sources = [source for source in sources if source is not None]
        within_months = requirement.temporal_window_months
        valid_source = None
        if within_months is not None:
            cutoff = today - timedelta(days=within_months * 30)
            for source in sources:
                activity_end = today if source.is_current else source.end_date
                if activity_end is not None and activity_end >= cutoff:
                    valid_source = source
                    break
        if valid_source is None:
            temporal_failure = {
                "type": "TEMPORAL",
                "requirement_id": requirement.id,
                "required": requirement.original_text,
                "reason": "Matched evidence could not be linked to a dated source within the requested time window",
            }
            if requirement.mandatory:
                failures.append(temporal_failure)
            matches.append({
                "type": "temporal", "requirement_id": requirement.id,
                "requirement": requirement.original_text, "matched": False, "evidence": [],
            })
        else:
            matches.append({
                "type": "temporal", "requirement_id": requirement.id,
                "requirement": requirement.original_text, "matched": True,
                "candidate_value": valid_source.end_date.isoformat() if valid_source.end_date else "ongoing",
                "evidence": dependency_evidence,
            })
    return failures, matches

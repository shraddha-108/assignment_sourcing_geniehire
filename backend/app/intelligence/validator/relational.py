from sqlalchemy.orm import Session
from app.search.normalization import role_matches as _role_matches
from app.intelligence.validator.rules import (
    _normalize_role_for_match,
    _normalize_for_source,
    _resolve_experience_source,
)

def validate_relational_requirements(
    db: Session,
    candidate_id: int,
    requirements: list,
    evidence: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Resolve SAME_SOURCE relationships over already validated evidence."""
    by_id = {item.id: item for item in requirements}
    failures = []
    matches = []
    for requirement in requirements:
        if requirement.relationship.upper() != "SAME_SOURCE":
            continue
        source_sets = []
        for dependency_id in requirement.dependencies:
            dependency = by_id.get(dependency_id)
            if dependency is None:
                source_sets.append(set())
                continue
            expected = _normalize_for_source(
                str(dependency.value) if isinstance(dependency.value, str)
                else dependency.normalized_text
            )
            sources = set()
            for item in evidence:
                if _normalize_for_source(item.get("requirement")) != expected:
                    continue
                if item.get("source_kind") == "experience_record":
                    sources.add(("experience", item.get("experience_id")))
                else:
                    resolved = _resolve_experience_source(db, candidate_id, item)
                    if resolved is not None:
                        sources.add(("experience", resolved.id))
                    elif item.get("source_id") is not None:
                        sources.add(("evidence", item.get("source_id")))
            source_sets.append(sources)
        common_sources = (
            set.intersection(*source_sets)
            if source_sets and all(source_sets)
            else set()
        )
        matched = bool(common_sources)
        if not matched and requirement.mandatory:
            failures.append({
                "type": "RELATIONAL", "requirement_id": requirement.id,
                "required": requirement.original_text,
                "reason": "Dependent requirements could not be resolved to the same evidence source",
            })
        matches.append({
            "type": "relational", "requirement_id": requirement.id,
            "requirement": requirement.original_text, "matched": matched,
            "relationship": "SAME_SOURCE", "evidence": [],
        })
    return failures, matches


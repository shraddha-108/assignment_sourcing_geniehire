import math
import re
from datetime import date


def _sigmoid(value: float) -> float:
    value = max(-60.0, min(60.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _evidence_quality(evidence: list[dict]) -> float:
    if not evidence:
        return 0.0

    source_weights = {
        "project": 1.0,
        "experience": 0.95,
        "summary": 0.8,
        "skills": 0.6,
        "skill": 0.6,
        "education": 0.45,
    }
    qualities = []
    for item in evidence:
        text = str(item.get("text") or "")
        source_weight = source_weights.get(
            str(item.get("evidence_type") or "").casefold(), 0.7
        )
        detail_weight = min(len(text.strip()) / 180.0, 1.0)
        support = float(item.get("semantic_support_score") or 0.0)
        qualities.append(
            0.65 * source_weight + 0.20 * detail_weight + 0.15 * support
        )
    return max(0.0, min(1.0, max(qualities)))


def _experience_fit(matched_requirements: list[dict]) -> float | None:
    match = next(
        (item for item in matched_requirements
         if item.get("type") == "experience" and item.get("matched", True)),
        None,
    )
    if not match:
        return None

    value = str(match.get("candidate_value") or "")
    try:
        parts = value.split()
        years = float(parts[0]) if parts else 0.0
        if len(parts) > 2 and parts[1].startswith("year"):
            years += float(parts[2]) / 12.0
    except (ValueError, IndexError):
        return 0.65

    requirement = str(match.get("requirement") or "")
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", requirement)]

    if len(numbers) >= 2 and "-" in requirement:
        low, high = numbers[0], numbers[1]
        midpoint = (low + high) / 2.0
        half_range = max((high - low) / 2.0, 0.5)
        return 0.70 + 0.30 * max(0.0, 1.0 - abs(years - midpoint) / half_range)
    if numbers:
        minimum = numbers[0]
        # Passing the minimum is qualification. Additional relevant experience
        # improves ranking gradually instead of giving every qualified person
        # the same full experience-fit value.
        extra_years = max(0.0, years - minimum)
        return 0.75 + 0.25 * min(extra_years / 5.0, 1.0)
    return 0.65


def _skill_fit(candidate, matched_requirements: list[dict]) -> float | None:
    requested = [
        item for item in matched_requirements
        if item.get("type") == "skill" and item.get("matched", True)
    ]
    if not requested:
        return None

    rows = getattr(candidate, "candidate_skills", []) or []
    fits = []
    today = date.today()
    for requirement in requested:
        name = " ".join(str(requirement.get("candidate_value") or
            requirement.get("requirement") or "").casefold().split())
        row = next((skill_row for skill_row in rows
            if getattr(skill_row, "skill", None)
            and " ".join(str(skill_row.skill.normalized_name or
                skill_row.skill.name).casefold().split()) == name), None)
        if row is None:
            continue

        months = row.months_of_experience
        if months is None and row.years_of_experience is not None:
            months = float(row.years_of_experience) * 12
        depth_fit = 0.65 + 0.35 * min(max(float(months or 0), 0.0) / 60.0, 1.0)

        if row.last_used_date:
            months_since_use = max(0, (today - row.last_used_date).days / 30.0)
            recency_fit = 0.60 + 0.40 * math.exp(-months_since_use / 60.0)
        else:
            recency_fit = 0.75

        confidence_fit = (
            max(0.0, min(float(row.confidence), 1.0))
            if row.confidence is not None else 0.75
        )
        fits.append(0.65 * depth_fit + 0.25 * recency_fit + 0.10 * confidence_fit)

    return sum(fits) / len(fits) if fits else None


def _role_fit(matched_requirements: list[dict]) -> float | None:
    roles = [item for item in matched_requirements
        if item.get("type") == "role" and item.get("matched", True)]
    if not roles:
        return None
    fits = []
    for item in roles:
        requested = set(str(item.get("requirement") or "").casefold().split())
        actual = set(str(item.get("candidate_value") or "").casefold().split())
        fits.append(len(requested & actual) / max(1, len(actual)))
    return sum(fits) / len(fits)


def _requirement_fit(matched_requirements: list[dict]) -> float | None:
    non_semantic = [
        item for item in matched_requirements
        if item.get("type") in {
            "skill", "company", "location", "experience", "role", "temporal", "relational"
        }
    ]
    soft = [item for item in matched_requirements if item.get("mandatory") is False]
    if soft:
        groups: dict[str, list[dict]] = {}
        independent = []
        for item in soft:
            if item.get("group_id") and str(item.get("relationship", "")).upper() == "OR":
                groups.setdefault(str(item["group_id"]), []).append(item)
            else:
                independent.append(item)
        outcomes = [bool(item.get("matched")) for item in independent]
        outcomes.extend(any(bool(item.get("matched")) for item in group)
                        for group in groups.values())
        return sum(outcomes) / len(outcomes) if outcomes else None
    if not non_semantic:
        return None
    return 1.0


def score_candidate(candidate, evidence: list[dict], item: dict) -> float:
    """Compute a transparent 45–95 score from validated fit and evidence."""
    if candidate is None:
        return 0.0

    validation = item.get("validation", {})
    matched = validation.get("matched_requirements", [])
    semantic_matches = [
        match for match in matched if match.get("type") == "semantic"
    ]
    semantic_support = max(
        (
            float(evidence_item.get("semantic_support_score") or 0.0)
            for match in semantic_matches
            for evidence_item in match.get("evidence", [])
        ),
        default=0.0,
    )
    ranking_evidence = item.get("ranking_evidence") or evidence
    candidate_validation_scores = [
        float(match["candidate_reranker_score"])
        for match in semantic_matches
        if match.get("candidate_reranker_score") is not None
    ]
    reranker_score = (
        max(candidate_validation_scores)
        if candidate_validation_scores
        else max(
            (float(ev.get("reranker_score") or 0.0) for ev in ranking_evidence),
            default=0.0,
        )
    )
    reranker_fit = _sigmoid(reranker_score) if any(
        ev.get("reranker_score") is not None for ev in ranking_evidence
    ) else 0.0
    evidence_fit = _evidence_quality(evidence)
    role_fit = _role_fit(matched)
    skill_fit = _skill_fit(candidate, matched)
    experience_fit = _experience_fit(matched)
    requirement_fit = _requirement_fit(matched)

    if semantic_matches:
        components = [
            (semantic_support, 0.50),
            (reranker_fit, 0.20),
            (evidence_fit, 0.20),
        ]
        structured_fit = [
            value for value in (role_fit, skill_fit, experience_fit, requirement_fit)
            if value is not None
        ]
        if structured_fit:
            components.append((sum(structured_fit) / len(structured_fit), 0.10))
    else:
        components = []
        if item.get("semantic_match"):
            components.extend([
                (reranker_fit, 0.55),
                (evidence_fit, 0.45),
            ])
        for value, weight in (
            (skill_fit, 0.30),
            (role_fit, 0.15),
            (experience_fit, 0.25),
            (evidence_fit, 0.20),
            (requirement_fit, 0.10),
        ):
            if value is not None:
                components.append((value, weight))

    weight_total = sum(weight for _, weight in components)
    signal = (
        sum(value * weight for value, weight in components) / weight_total
        if weight_total
        else 0.65
    )
    # The 45-point baseline represents validated hard requirements. The
    # remaining 50 points reward evidence quality and closeness of fit.
    return round(45.0 + 50.0 * max(0.0, min(signal, 1.0)), 4) / 100.0


def score_candidates(
    candidates: list[dict],
    structured_requirements: dict | None = None,
) -> list[dict]:
    scored = []
    for item in candidates:
        result = dict(item)
        result["score"] = score_candidate(
            candidate=item.get("candidate"),
            evidence=item.get("evidence") or [],
            item=item,
        )
        scored.append(result)
    return scored

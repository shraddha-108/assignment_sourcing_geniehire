import re


DEFAULT_RECENT_MONTHS = 12
DEFAULT_LIMIT = 10
MAX_LIMIT = 100


ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "postgres": "postgresql",
    "reactjs": "react",
    "node": "nodejs",
}


def _word_pattern(word: str) -> str:
    return rf"(?<![\w+#]){re.escape(word)}(?![\w+#])"


def _extract_requested_count(query: str) -> tuple[int, str]:
    patterns = [
        r"\b(?:find|get|show|return|give|bring)\s+(?:me\s+)?(\d+)\b",
        r"\btop\s+(\d+)\b",
        r"\b(\d+)\s+(?:candidates?|people|developers?|engineers?)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)

        if match:
            count = int(match.group(1))
            count = max(1, min(count, MAX_LIMIT))

            cleaned_query = (
                query[:match.start()]
                + query[match.end():]
            )

            return count, cleaned_query

    return DEFAULT_LIMIT, query


def _extract_recency(query: str) -> tuple[int | None, str]:
    patterns = [
        r"\b(?:last|past|previous)\s+(\d+)\s*(months?|years?)\b",
        r"\b(?:last|past)\s+year\b",
        r"\b(?:recent|recently|currently|latest)\b",
    ]

    match = re.search(patterns[0], query, re.IGNORECASE)

    if match:
        value = int(match.group(1))
        unit = match.group(2).lower()

        months = value * 12 if unit.startswith("year") else value

        cleaned_query = (
            query[:match.start()]
            + query[match.end():]
        )

        return months, cleaned_query

    match = re.search(patterns[1], query, re.IGNORECASE)

    if match:
        cleaned_query = (
            query[:match.start()]
            + query[match.end():]
        )

        return 12, cleaned_query

    match = re.search(patterns[2], query, re.IGNORECASE)

    if match:
        cleaned_query = (
            query[:match.start()]
            + query[match.end():]
        )

        return DEFAULT_RECENT_MONTHS, cleaned_query

    return None, query


def _extract_experience(query: str) -> tuple[int | None, str]:
    patterns = [
        r"\b(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience\b",
        r"\bexperience\s+(?:of\s+)?(\d+)\+?\s*(?:years?|yrs?)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)

        if match:
            years = int(match.group(1))

            cleaned_query = (
                query[:match.start()]
                + query[match.end():]
            )

            return years, cleaned_query

    return None, query


def _extract_skills(
    query: str,
    known_skills: list[str],
) -> list[str]:

    known = {
        skill.lower()
        for skill in known_skills
    }

    terms = {
        skill: skill
        for skill in known
    }

    for alias, canonical in ALIASES.items():
        if canonical in known:
            terms[alias] = canonical

    skills = []

    for term, canonical in terms.items():

        if re.search(_word_pattern(term), query):

            if canonical not in skills:
                skills.append(canonical)

    return skills


def parse_query(
    query: str,
    known_skills: list[str],
) -> dict:

    q = query.strip().lower()

    requested_count, q = _extract_requested_count(q)

    recency_months, q = _extract_recency(q)

    experience_min_years, q = _extract_experience(q)

    skills = _extract_skills(
        q,
        known_skills,
    )

    semantic_requirement = q.strip()

    return {
        "requested_count": requested_count,
        "structured_requirements": {
            "skills": skills,
            "recency_months": recency_months,
            "experience_min_years": experience_min_years,
        },
        "semantic_requirement": (
            semantic_requirement
            if semantic_requirement
            else None
        ),
    }
import re

DEFAULT_RECENT_MONTHS = 12   # what "recently" means
DEFAULT_LIMIT = 10
MAX_LIMIT = 100

# Common shorthand -> the normalized skill stored in the database
ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "postgres": "postgresql",
    "reactjs": "react",
    "node": "nodejs",
}


def _word_pattern(word: str) -> str:
    # whole-word match that also works for names like "c++" or "c#"
    return rf"(?<![\w+#]){re.escape(word)}(?![\w+#])"


def parse_query(query: str, known_skills: list[str]) -> dict:
    q = query.lower()

    # --- recency ---
    recency_months = None

    m = re.search(r"(?:last|past|previous)\s+(\d+)\s*(months?|years?)\b", q)
    if m:
        n = int(m.group(1))
        recency_months = n * 12 if m.group(2).startswith("year") else n
        q = q.replace(m.group(0), " ")
    elif re.search(r"(?:last|past)\s+year\b", q):
        recency_months = 12
        q = re.sub(r"(?:last|past)\s+year\b", " ", q)
    elif re.search(r"\b(recent|recently|currently|latest)\b", q):
        recency_months = DEFAULT_RECENT_MONTHS

    # --- limit (first number left after removing the recency phrase) ---
    limit = DEFAULT_LIMIT
    m = re.search(r"\b(\d+)\b", q)
    if m:
        limit = max(1, min(int(m.group(1)), MAX_LIMIT))

    # --- skills ---
    known = {s.lower() for s in known_skills}
    terms = {s: s for s in known}
    for alias, canonical in ALIASES.items():
        if canonical in known:
            terms[alias] = canonical

    skills: list[str] = []
    for term, canonical in terms.items():
        if re.search(_word_pattern(term), q) and canonical not in skills:
            skills.append(canonical)

    return {"skills": skills, "recency_months": recency_months, "limit": limit}
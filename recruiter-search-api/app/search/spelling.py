"""Small, conservative spell suggestions for recruiter search queries."""

import re


_SEARCH_VOCABULARY = set("""
candidate candidates recruiter recruiters developer developers engineer engineers
software backend frontend fullstack full stack data analyst analytics scientist
manager management senior junior lead fresher graduate experience experienced
year years month months worked work working built build building developed develop
development designed design designing created create creating implemented implement
integrated integration products product project projects system systems platform
platforms scalable distributed architecture cloud database databases application
applications python java javascript typescript react node angular django flask fastapi
sql postgresql mysql mongodb oracle aws azure gcp docker kubernetes api apis rest
microservices d365 dynamics microsoft crm erp finance salesforce power powerplatform
machine learning artificial intelligence ai ml llm llms genai chatbot chatbots rag
ecommerce e-commerce pune mumbai maharashtra india location remote hybrid
with who has have in on for of and the a an to at looking find search
""".split())

_PROTECTED_TERMS = {
    "ai", "ml", "llm", "llms", "d365", "crm", "erp", "sql", "api", "apis",
    "aws", "gcp", "java", "python", "react", "node", "node.js", "c++", "c#",
    "sap", "erp", "usa", "uk", "india",
}


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def suggest_query_correction(query: str) -> str | None:
    """Return a conservative corrected query when a clear typo is present."""
    parts = []
    cursor = 0
    changed = False
    for match in list(re.finditer(r"[A-Za-z][A-Za-z'-]*", query)):
        parts.append(query[cursor:match.start()])
        original = match.group(0)
        word = original.casefold()
        if len(word) < 4 or word in _PROTECTED_TERMS or word in _SEARCH_VOCABULARY:
            parts.append(original)
            cursor = match.end()
            continue

        max_distance = 1 if len(word) < 8 else 2
        candidates = [
            ( _edit_distance(word, candidate), candidate)
            for candidate in _SEARCH_VOCABULARY
            if abs(len(word) - len(candidate)) <= max_distance
        ]
        if not candidates:
            parts.append(original)
            cursor = match.end()
            continue
        best_distance = min(distance for distance, _ in candidates)
        best = sorted(candidate for distance, candidate in candidates if distance == best_distance)
        if best_distance == 0 or best_distance > max_distance or len(best) != 1:
            parts.append(original)
            cursor = match.end()
            continue

        corrected = best[0]
        if original.isupper():
            corrected = corrected.upper()
        elif original[:1].isupper():
            corrected = corrected.capitalize()
        parts.append(corrected)
        cursor = match.end()
        changed = True

    parts.append(query[cursor:])
    suggestion = "".join(parts)
    return suggestion if changed and suggestion.casefold() != query.casefold() else None

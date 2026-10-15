import re
from datetime import date


SKILL_ALIASES = {
    "python": "python",
    "python3": "python",
    "py": "python",
    "javascript": "javascript",
    "java script": "javascript",
    "js": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
    "react": "react",
    "reactjs": "react",
    "react.js": "react",
    "node": "nodejs",
    "nodejs": "nodejs",
    "node.js": "nodejs",
    "express": "express",
    "fastapi": "fastapi",
    "django": "django",
    "flask": "flask",
    "sql": "sql",
    "mysql": "mysql",
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "mongodb": "mongodb",
    "mongo db": "mongodb",
    "redis": "redis",
    "docker": "docker",
    "kubernetes": "kubernetes",
    "aws": "aws",
    "azure": "azure",
    "gcp": "gcp",
    "git": "git",
    "github": "github",
    "pytorch": "pytorch",
    "tensorflow": "tensorflow",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "machine learning": "machine learning",
    "deep learning": "deep learning",
    "nlp": "nlp",
    "natural language processing": "nlp",
    "llm": "llm",
    "large language model": "llm",
    "langchain": "langchain",
    "langgraph": "langgraph",
    "rag": "rag",
    "generative ai": "generative ai",
    "artificial intelligence": "artificial intelligence",
}


def _pattern(term: str) -> str:
    return rf"(?<![\w+#.]){re.escape(term)}(?![\w+#.])"


def extract_skills(text: str) -> list[str]:
    normalized = text.lower()
    found = set()

    for alias, canonical in SKILL_ALIASES.items():
        if re.search(_pattern(alias), normalized):
            found.add(canonical)

    return sorted(found)


def build_skill_records(
    text: str,
    experiences: list[dict],
) -> list[dict]:
    skills = extract_skills(text)

    latest_end_date = None
    total_experience_months = 0

    for experience in experiences:
        start_date = experience.get("start_date")
        end_date = experience.get("end_date") or date.today()

        if not start_date:
            continue

        if end_date < start_date:
            continue

        months = (
            (end_date.year - start_date.year) * 12
            + end_date.month
            - start_date.month
        )

        total_experience_months += max(months, 0)

        if latest_end_date is None or end_date > latest_end_date:
            latest_end_date = end_date

    return [
        {
            "skill": skill,
            "last_used_date": latest_end_date,
            "total_months": total_experience_months,
        }
        for skill in skills
    ]
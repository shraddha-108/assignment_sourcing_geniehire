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


def calculate_months(
    start_date: date,
    end_date: date,
) -> int:
    if end_date < start_date:
        return 0

    return max(
        (
            (end_date.year - start_date.year) * 12
            + end_date.month
            - start_date.month
        ),
        0,
    )


def merge_date_ranges(
    ranges: list[tuple[date, date]],
) -> list[tuple[date, date]]:
    if not ranges:
        return []

    sorted_ranges = sorted(
        ranges,
        key=lambda item: item[0],
    )

    merged = [sorted_ranges[0]]

    for current_start, current_end in sorted_ranges[1:]:
        previous_start, previous_end = merged[-1]

        if current_start <= previous_end:
            merged[-1] = (
                previous_start,
                max(previous_end, current_end),
            )
        else:
            merged.append(
                (current_start, current_end)
            )

    return merged


def calculate_total_experience_months(
    experiences: list[dict],
) -> int:
    ranges = []

    for experience in experiences:
        start_date = experience.get("start_date")
        end_date = experience.get("end_date")

        if not start_date:
            continue

        if not end_date:
            end_date = date.today()

        if end_date < start_date:
            continue

        ranges.append(
            (start_date, end_date)
        )

    merged_ranges = merge_date_ranges(ranges)

    return sum(
        calculate_months(start_date, end_date)
        for start_date, end_date in merged_ranges
    )


def extract_experience_skills(
    experience: dict,
) -> list[str]:
    evidence = experience.get("evidence", "")

    if not evidence:
        return []

    return extract_skills(evidence)


def build_skill_records(
    text: str,
    experiences: list[dict],
) -> list[dict]:
    all_skills = extract_skills(text)

    skill_ranges: dict[str, list[tuple[date, date]]] = {
        skill: []
        for skill in all_skills
    }

    for experience in experiences:
        start_date = experience.get("start_date")
        end_date = experience.get("end_date")

        if not start_date:
            continue

        if not end_date:
            end_date = date.today()

        if end_date < start_date:
            continue

        experience_skills = extract_experience_skills(
            experience
        )

        for skill in experience_skills:
            if skill not in skill_ranges:
                skill_ranges[skill] = []

            skill_ranges[skill].append(
                (start_date, end_date)
            )

    records = []

    for skill in sorted(skill_ranges):
        ranges = merge_date_ranges(
            skill_ranges[skill]
        )

        total_months = sum(
            calculate_months(start_date, end_date)
            for start_date, end_date in ranges
        )

        last_used_date = None

        if ranges:
            last_used_date = max(
                end_date
                for _, end_date in ranges
            )

        records.append(
            {
                "skill": skill,
                "last_used_date": last_used_date,
                "total_months": total_months,
            }
        )

    return records
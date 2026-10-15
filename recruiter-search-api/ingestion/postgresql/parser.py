import re

from ingestion.postgresql.experience_extractor import extract_experiences
from ingestion.postgresql.skill_extractor import build_skill_records


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = []

    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


def extract_email(text: str) -> str | None:
    match = re.search(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        text,
    )

    return match.group(0).lower() if match else None


def extract_phone(text: str) -> str | None:
    patterns = [
        r"\+91[\s-]?\d{10}",
        r"\b\d{10}\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return match.group(0)

    return None


def extract_name(text: str, filename: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines[:10]:
        if "@" in line:
            continue

        if re.search(r"\d", line):
            continue

        if len(line.split()) >= 2 and len(line) <= 80:
            return line

    name = re.sub(r"\.[^.]+$", "", filename)
    name = re.sub(r"\[[^\]]*\]", "", name)
    name = re.sub(r"^Naukri_", "", name)
    name = re.sub(r"[_-]+", " ", name)

    return name.strip()


def parse_resume(text: str, filename: str) -> dict:
    cleaned_text = clean_text(text)

    experiences = extract_experiences(cleaned_text)

    skills = build_skill_records(
        text=cleaned_text,
        experiences=experiences,
    )

    return {
        "name": extract_name(cleaned_text, filename),
        "email": extract_email(cleaned_text),
        "phone": extract_phone(cleaned_text),
        "experiences": experiences,
        "skills": skills,
    }
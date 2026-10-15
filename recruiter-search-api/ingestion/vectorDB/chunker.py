import re


SECTION_PATTERNS = {
    "summary": [
        r"summary",
        r"profile",
        r"professional summary",
        r"career summary",
        r"about me",
        r"objective",
        r"career objective",
        r"profile summary",
    ],
    "technical_skills": [
        r"technical skills",
        r"technical skill",
        r"skills",
        r"key skills",
        r"core skills",
        r"core competencies",
        r"skills summary",
        r"technical expertise",
        r"technologies",
        r"technology stack",
    ],
    "experience": [
        r"experience",
        r"work experience",
        r"professional experience",
        r"employment history",
        r"work history",
        r"professional experience",
    ],
    "projects": [
        r"projects",
        r"personal projects",
        r"academic projects",
        r"key projects",
        r"project experience",
    ],
    "achievements": [
        r"achievements",
        r"accomplishments",
        r"awards",
        r"honors",
    ],
    "education": [
        r"education",
        r"academic background",
        r"qualifications",
        r"educational background",
    ],
}


def normalize_heading(line: str) -> str:
    line = line.strip().lower()
    line = re.sub(r"[^a-z\s]", " ", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def detect_section(line: str) -> str | None:
    normalized = normalize_heading(line)

    for section, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            if re.fullmatch(pattern, normalized):
                return section

    return None


def detect_inline_section(line: str) -> tuple[str | None, str]:
    original = line.strip()
    normalized = normalize_heading(original)

    for section, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            if re.match(
                rf"^{pattern}(?:\s*[:\-–—]\s*|\s+|$)",
                normalized,
                re.IGNORECASE,
            ):
                match = re.match(
                    rf"^{pattern}(?:\s*[:\-–—]\s*|\s+|$)",
                    original,
                    re.IGNORECASE,
                )

                if match:
                    remaining = original[match.end():].strip()
                    return section, remaining

    return None, original


def split_into_chunks(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[str]:
    words = text.split()

    if not words:
        return []

    chunks = []
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))

        chunk = " ".join(words[start:end]).strip()

        if chunk:
            chunks.append(chunk)

        if end == len(words):
            break

        start = end - overlap

    return chunks


def create_chunks(
    candidate_id: int,
    text: str,
) -> list[dict]:
    lines = text.splitlines()

    sections = []
    current_section = "summary"
    current_lines = []

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            continue

        exact_section = detect_section(line)

        if exact_section:
            if current_lines:
                sections.append({
                    "section": current_section,
                    "text": "\n".join(current_lines),
                })

            current_section = exact_section
            current_lines = []
            continue

        inline_section, remaining_text = detect_inline_section(line)

        if inline_section:
            if current_lines:
                sections.append({
                    "section": current_section,
                    "text": "\n".join(current_lines),
                })

            current_section = inline_section
            current_lines = []

            if remaining_text:
                current_lines.append(remaining_text)

            continue

        current_lines.append(line)

    if current_lines:
        sections.append({
            "section": current_section,
            "text": "\n".join(current_lines),
        })

    chunks = []
    chunk_id = 0

    for section in sections:

        if section["section"] == "technical_skills":
            continue

        text_chunks = split_into_chunks(
            section["text"]
        )

        for chunk_text in text_chunks:
            chunks.append({
                "candidate_id": candidate_id,
                "chunk_id": chunk_id,
                "chunk_type": section["section"],
                "section": section["section"],
                "text": chunk_text,
            })

            chunk_id += 1

    return chunks
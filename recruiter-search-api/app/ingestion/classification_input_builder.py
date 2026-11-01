
import re


SECTION_ALIASES = {
    "summary": {
        "summary",
        "professional summary",
        "career summary",
        "profile",
        "professional profile",
        "about me",
        "objective",
        "career objective",
    },
    "experience": {
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "work history",
        "career history",
    },
    "projects": {
        "projects",
        "personal projects",
        "professional projects",
        "academic projects",
        "key projects",
    },
    "skills": {
        "skills",
        "technical skills",
        "core skills",
        "core competencies",
        "technical expertise",
        "areas of expertise",
    },
    "education": {
        "education",
        "educational background",
        "academic background",
        "academic qualifications",
        "educational qualifications",
    },
    "certifications": {
        "certifications",
        "certificates",
        "licenses",
        "professional certifications",
    },
    "achievements": {
        "achievements",
        "accomplishments",
        "awards",
        "honors",
    },
    "internships": {
        "internships",
        "internship experience",
    },
    "training": {
        "training",
        "courses",
        "professional training",
    },
    "publications": {
        "publications",
        "research",
        "papers",
    },
}


HEADING_TO_SECTION = {
    heading: section
    for section, headings in SECTION_ALIASES.items()
    for heading in headings
}


# Common terms indicating a professional title.
ROLE_HINTS = {
    "developer",
    "engineer",
    "analyst",
    "manager",
    "consultant",
    "designer",
    "architect",
    "administrator",
    "specialist",
    "coordinator",
    "director",
    "executive",
    "recruiter",
    "marketer",
    "marketing",
    "accountant",
    "researcher",
    "scientist",
    "technician",
    "intern",
    "founder",
    "owner",
    "lead",
    "leader",
    "officer",
    "associate",
    "professional",
    "sales",
    "finance",
    "operations",
    "product",
    "teacher",
    "lawyer",
    "hr",
    "support",
}


EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

URL_PATTERN = re.compile(
    r"\b(?:https?://|www\.|linkedin\.com/|github\.com/)\S+",
    re.IGNORECASE,
)

PHONE_LABEL_PATTERN = re.compile(
    r"\b(?:phone|mobile|telephone|tel|contact\s*(?:number|no\.?))"
    r"\s*[:\-]?\s*\+?[\d\s().-]{7,}",
    re.IGNORECASE,
)

CONTACT_HEADER_PATTERN = re.compile(
    r"^\s*(?:email|e-mail|phone|mobile|contact|telephone|tel|"
    r"address|location|linkedin|github|portfolio|website)"
    r"\s*[:|]",
    re.IGNORECASE,
)

LOCATION_HEADER_PATTERN = re.compile(
    r"^\s*(?:city|state|country|present location|current location)"
    r"\s*[:|]",
    re.IGNORECASE,
)


def normalize_heading(text: str) -> str:
    """Normalize a possible resume section heading."""

    text = text.strip()

    # Remove bullets and other heading prefixes.
    text = re.sub(r"^[\s•·▪◦*-]+", "", text)

    text = text.lower()

    # Normalize whitespace.
    text = re.sub(r"\s+", " ", text)

    # Remove trailing heading punctuation.
    text = re.sub(r"[\s:|–—-]+$", "", text)

    return text.strip()


def detect_section_heading(
    line: str,
) -> tuple[str | None, str]:
    """
    Detect a known section heading.

    Supports both:
        WORK EXPERIENCE

    And:
        SKILLS: Python, FastAPI, React

    Returns:
        (section_name, remaining_content)
    """

    cleaned = line.strip()

    cleaned = re.sub(
        r"^[\s•·▪◦*-]+",
        "",
        cleaned,
    )

    # First, check whether the entire line is a heading.
    normalized = normalize_heading(cleaned)

    if normalized in HEADING_TO_SECTION:
        return HEADING_TO_SECTION[normalized], ""

    # Check inline headings such as "Skills: Python, React".
    for separator in (":", "|"):
        heading, sep, remaining = cleaned.partition(separator)

        if not sep:
            continue

        normalized = normalize_heading(heading)

        if normalized in HEADING_TO_SECTION:
            return (
                HEADING_TO_SECTION[normalized],
                remaining.strip(),
            )

    return None, ""


def clean_professional_line(line: str) -> str:
    """
    Remove identifiable contact details from a line.

    The remaining professional content is preserved.
    """

    line = EMAIL_PATTERN.sub("", line)

    line = URL_PATTERN.sub("", line)

    line = PHONE_LABEL_PATTERN.sub("", line)

    return re.sub(r"\s+", " ", line).strip()


def is_likely_personal_name(line: str) -> bool:
    """
    Basic heuristic to identify a candidate name.

    Intended for the first line/segment of the resume header.
    This is not a general-purpose named-entity recognizer.
    """

    words = re.findall(r"[A-Za-z]+", line)

    if not 2 <= len(words) <= 4:
        return False

    if len(line) > 40:
        return False

    # Don't mistake professional titles for names.
    if any(word.lower() in ROLE_HINTS for word in words):
        return False

    # Names are generally title case or uppercase.
    correctly_cased = all(
        word.isupper() or word[0].isupper()
        for word in words
    )

    return correctly_cased


def looks_like_professional_headline(line: str) -> bool:
    """Check whether a line looks like a professional title."""

    words = set(re.findall(r"[A-Za-z]+", line.lower()))

    return bool(words.intersection(ROLE_HINTS))


def extract_header_information(
    lines: list[str],
) -> tuple[str | None, str | None]:
    """
    Process text occurring before the first recognized section.

    Extracts:
    - Professional headline
    - Other useful professional header content

    Excludes likely name and contact information.
    """

    segments: list[str] = []

    for line in lines:
        # Split combined header lines:
        # John Doe | Full Stack Developer | Pune
        pieces = re.split(r"\s*[|•·]\s*", line)

        for piece in pieces:
            piece = piece.strip()

            if not piece:
                continue

            # Don't send identifiable contact-only lines.
            if CONTACT_HEADER_PATTERN.match(piece):
                continue

            if LOCATION_HEADER_PATTERN.match(piece):
                continue

            piece = clean_professional_line(piece)

            if piece:
                segments.append(piece)

    # Usually the first header segment is the candidate's name.
    if segments and is_likely_personal_name(segments[0]):
        segments.pop(0)

    if not segments:
        return None, None

    headline = None

    # Prefer a segment containing a professional role.
    for index, segment in enumerate(segments):
        if looks_like_professional_headline(segment):
            headline = segment
            segments.pop(index)
            break

    # Fallback: retain a short, title-like first line.
    if headline is None and segments:
        candidate = segments[0]

        if (
            len(candidate.split()) <= 7
            and not re.search(r"[.!?]\s*$", candidate)
        ):
            headline = candidate
            segments.pop(0)

    other_content = "\n".join(segments).strip()

    return headline, other_content or None


def split_resume_sections(text: str) -> dict[str, str]:
    """
    Split raw resume text into recognized sections.

    Text before the first recognized heading is treated
    as the resume header.
    """

    lines = text.splitlines()

    sections: dict[str, list[str]] = {
        section: []
        for section in SECTION_ALIASES
    }

    header_lines: list[str] = []

    current_section: str | None = None

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue

        section, remaining = detect_section_heading(stripped)

        if section:
            current_section = section

            # Support content on the same line as a heading.
            if remaining:
                sections[current_section].append(remaining)

            continue

        if current_section is None:
            header_lines.append(stripped)
        else:
            sections[current_section].append(stripped)

    # Process the resume header separately.
    headline, other_header = extract_header_information(
        header_lines
    )

    result: dict[str, str] = {}

    if headline:
        result["headline"] = headline

    for section, content in sections.items():
        cleaned_lines = [
            clean_professional_line(line)
            for line in content
        ]

        cleaned_content = "\n".join(
            line for line in cleaned_lines if line
        ).strip()

        if cleaned_content:
            result[section] = cleaned_content

    if other_header:
        result["other"] = other_header

    return result


def build_classification_input(text: str) -> str:
    """
    Build professional information for resume-domain classification.

    Input:
        Complete raw resume text.

    Output:
        Selected professional information as readable text.
    """

    sections = split_resume_sections(text)

    selected_sections = [
        "headline",
        "summary",
        "experience",
        "projects",
        "skills",
        "internships",
        "education",
        "certifications",
        "achievements",
        "training",
        "publications",
    ]

    parts: list[str] = []

    for section in selected_sections:
        content = sections.get(section)

        if not content:
            continue

        parts.append(
            f"{section.upper()}:\n{content}"
        )

    # Preserve information under unfamiliar headings
    # or unrecognized resume header content.
    other = sections.get("other")

    if other:
        parts.append(
            f"OTHER PROFESSIONAL CONTENT:\n{other}"
        )

    return "\n\n".join(parts)

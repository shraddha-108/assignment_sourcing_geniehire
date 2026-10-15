import re
from datetime import date


SECTION_HEADERS = {
    "experience",
    "work experience",
    "professional experience",
    "employment history",
    "employment",
    "career history",
    "work history",
}


STOP_HEADERS = {
    "education",
    "educational qualifications",
    "skills",
    "technical skills",
    "computer skills",
    "projects",
    "certifications",
    "achievements",
    "summary",
    "objective",
    "details",
}


DATE_PATTERN = re.compile(
    r"(?P<start_month>"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|sept|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?|\d{1,2}"
    r")?"
    r"\s*"
    r"(?P<start_year>19\d{2}|20\d{2})"
    r"\s*(?:-|to|–|—)\s*"
    r"(?P<end_month>"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|sept|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?|\d{1,2}"
    r")?"
    r"\s*"
    r"(?P<end_year>19\d{2}|20\d{2}|present|current|now)",
    re.IGNORECASE,
)


MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


KNOWN_TITLES = [
    "talent acquisition executive",
    "recruitment consultant",
    "software engineer",
    "senior software engineer",
    "developer",
    "engineer",
    "manager",
    "consultant",
    "recruiter",
    "hr executive",
    "hr recruiter",
]


def normalize_header(line: str) -> str:
    line = line.strip().lower()
    line = re.sub(r"[:\-–—]+$", "", line)
    line = re.sub(r"[^a-z\s]", "", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def find_experience_section(text: str) -> str:
    lines = text.splitlines()

    start_index = None

    for index, line in enumerate(lines):
        normalized = normalize_header(line)

        if normalized in SECTION_HEADERS:
            start_index = index + 1
            break

    if start_index is None:
        return ""

    section_lines = []

    for line in lines[start_index:]:
        normalized = normalize_header(line)

        if normalized in STOP_HEADERS:
            break

        section_lines.append(line)

    return "\n".join(section_lines)


def parse_month(value: str | None) -> int | None:
    if not value:
        return None

    value = value.lower().strip()

    if value.isdigit():
        return max(1, min(int(value), 12))

    return MONTHS.get(value)


def parse_date(
    month: str | None,
    year: str,
    is_end: bool = False,
) -> date:
    if year.lower() in {"present", "current", "now"}:
        return date.today()

    parsed_year = int(year)
    parsed_month = parse_month(month)

    if parsed_month is None:
        parsed_month = 12 if is_end else 1

    return date(parsed_year, parsed_month, 1)


def extract_date_range(text: str):
    match = DATE_PATTERN.search(text)

    if not match:
        return None

    start_date = parse_date(
        match.group("start_month"),
        match.group("start_year"),
    )

    end_date = parse_date(
        match.group("end_month"),
        match.group("end_year"),
        is_end=True,
    )

    if end_date < start_date:
        return None

    return start_date, end_date


def clean_line(line: str) -> str:
    line = re.sub(r"[•▪●◦]", " ", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def extract_table_experiences(lines: list[str]) -> list[dict]:
    experiences = []

    for line in lines:
        line = clean_line(line)

        if not line:
            continue

        normalized = normalize_header(line)

        if normalized == "organization role duration":
            continue

        date_range = extract_date_range(line)

        if not date_range:
            continue

        date_match = DATE_PATTERN.search(line)

        if not date_match:
            continue

        before_date = line[:date_match.start()].strip()

        lower_before_date = before_date.lower()

        title = None
        company = None

        for known_title in sorted(KNOWN_TITLES, key=len, reverse=True):
            if known_title in lower_before_date:
                title_start = lower_before_date.index(known_title)

                company = before_date[:title_start].strip()

                title = before_date[
                    title_start:title_start + len(known_title)
                ].strip()

                break

        if not company or not title:
            continue

        start_date, end_date = date_range

        experiences.append(
            {
                "company": company,
                "title": title,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    return experiences


def extract_separate_line_experiences(lines: list[str]) -> list[dict]:
    experiences = []

    for index in range(len(lines) - 2):
        company = clean_line(lines[index])
        title = clean_line(lines[index + 1])
        date_line = clean_line(lines[index + 2])

        if not company or not title:
            continue

        if extract_date_range(company):
            continue

        if extract_date_range(title):
            continue

        date_range = extract_date_range(date_line)

        if not date_range:
            continue

        if normalize_header(company) in STOP_HEADERS:
            continue

        if normalize_header(company) in SECTION_HEADERS:
            continue

        experiences.append(
            {
                "company": company.rstrip(":"),
                "title": title,
                "start_date": date_range[0],
                "end_date": date_range[1],
            }
        )

    return experiences


def deduplicate_experiences(experiences: list[dict]) -> list[dict]:
    unique = []
    seen = set()

    for experience in experiences:
        key = (
            experience["company"].lower(),
            experience["title"].lower(),
            experience["start_date"],
            experience["end_date"],
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(experience)

    return unique


def extract_experiences(text: str) -> list[dict]:
    section = find_experience_section(text)

    if not section:
        return []

    lines = [
        clean_line(line)
        for line in section.splitlines()
        if clean_line(line)
    ]

    table_experiences = extract_table_experiences(lines)

    separate_line_experiences = extract_separate_line_experiences(lines)

    experiences = table_experiences + separate_line_experiences

    return deduplicate_experiences(experiences)
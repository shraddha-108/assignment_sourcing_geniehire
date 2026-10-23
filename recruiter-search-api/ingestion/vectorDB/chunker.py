import re
from datetime import date, datetime


DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 50


def _to_iso_date(
    value,
) -> str | None:
    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        return value.date().isoformat()

    if isinstance(
        value,
        date,
    ):
        return value.isoformat()

    value = str(value).strip()

    if not value:
        return None

    return value


def _split_long_text(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    words = text.split()

    if not words:
        return []

    chunks = []
    start = 0

    while start < len(words):

        end = min(
            start + chunk_size,
            len(words),
        )

        chunk = " ".join(
            words[start:end]
        ).strip()

        if chunk:
            chunks.append(chunk)

        if end == len(words):
            break

        next_start = end - overlap

        if next_start <= start:
            next_start = end

        start = next_start

    return chunks


def _extract_evidence_units(
    text: str,
) -> list[str]:
    """
    Preserve natural evidence boundaries before
    combining them into retrieval chunks.

    Resume evidence commonly contains:
    - bullet points
    - separate responsibilities
    - separate project statements
    - paragraphs

    We preserve those boundaries instead of immediately
    flattening everything into one 500-word block.
    """

    if not text:
        return []

    normalized = text.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    raw_lines = normalized.split("\n")

    units = []

    for line in raw_lines:

        line = line.strip()

        if not line:
            continue

        # Remove common bullet markers while preserving
        # the actual evidence wording.
        line = re.sub(
            r"^[\-\*\u2022\u2023\u25E6]+\s*",
            "",
            line,
        ).strip()

        if not line:
            continue

        units.append(line)

    if units:
        return units

    return [
        normalized.strip()
    ]


def _build_chunks_from_units(
    units: list[str],
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """
    Combine nearby evidence units while preserving
    their natural boundaries.

    A single evidence unit larger than chunk_size is
    split independently.
    """

    chunks = []
    current_units = []
    current_word_count = 0

    for unit in units:

        unit_word_count = len(
            unit.split()
        )

        if unit_word_count > chunk_size:

            if current_units:
                chunks.append(
                    "\n".join(
                        current_units
                    ).strip()
                )

                current_units = []
                current_word_count = 0

            long_chunks = _split_long_text(
                text=unit,
                chunk_size=chunk_size,
                overlap=overlap,
            )

            chunks.extend(
                long_chunks
            )

            continue

        if (
            current_units
            and current_word_count
            + unit_word_count
            > chunk_size
        ):
            chunks.append(
                "\n".join(
                    current_units
                ).strip()
            )

            # Keep a small amount of recent context.
            overlap_units = []
            overlap_words = 0

            for previous_unit in reversed(
                current_units
            ):
                previous_words = len(
                    previous_unit.split()
                )

                if (
                    overlap_words
                    + previous_words
                    > overlap
                ):
                    break

                overlap_units.insert(
                    0,
                    previous_unit,
                )

                overlap_words += previous_words

            current_units = overlap_units
            current_word_count = overlap_words

        current_units.append(unit)
        current_word_count += unit_word_count

    if current_units:
        chunks.append(
            "\n".join(
                current_units
            ).strip()
        )

    return [
        chunk
        for chunk in chunks
        if chunk
    ]


def split_into_chunks(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """
    Split text into retrieval-friendly chunks.

    Unlike the previous implementation, this first
    respects natural line/bullet boundaries and only
    splits individual evidence units when they are
    larger than the target size.
    """

    if not text or not text.strip():
        return []

    units = _extract_evidence_units(
        text
    )

    return _build_chunks_from_units(
        units=units,
        chunk_size=chunk_size,
        overlap=overlap,
    )


def create_chunks(
    candidate_id: int,
    candidate_data: dict,
) -> list[dict]:

    chunks = []
    chunk_id = 0

    evidence = candidate_data.get(
        "evidence",
        {},
    )

    # ---------------------------------------------------------
    # SUMMARY
    # ---------------------------------------------------------

    summary = evidence.get(
        "summary",
        "",
    )

    if summary:

        for chunk_text in split_into_chunks(
            summary
        ):
            chunks.append(
                {
                    "candidate_id": candidate_id,
                    "chunk_id": chunk_id,
                    "chunk_type": "summary",
                    "section": "summary",
                    "text": chunk_text,
                }
            )

            chunk_id += 1

    # ---------------------------------------------------------
    # EXPERIENCE
    # ---------------------------------------------------------

    for experience in candidate_data.get(
        "experiences",
        [],
    ):

        experience_evidence = experience.get(
            "evidence",
            "",
        )

        if not experience_evidence:
            continue

        company = experience.get(
            "company"
        )

        title = experience.get(
            "title"
        )

        start_date = _to_iso_date(
            experience.get(
                "start_date"
            )
        )

        end_date = _to_iso_date(
            experience.get(
                "end_date"
            )
        )

        text_chunks = split_into_chunks(
            experience_evidence
        )

        for chunk_text in text_chunks:

            chunks.append(
                {
                    "candidate_id": candidate_id,
                    "chunk_id": chunk_id,
                    "chunk_type": "experience",
                    "section": "experience",
                    "company": company,
                    "job_title": title,
                    "start_date": start_date,
                    "end_date": end_date,
                    "text": chunk_text,
                }
            )

            chunk_id += 1

    # ---------------------------------------------------------
    # PROJECTS
    # ---------------------------------------------------------

    for project in evidence.get(
        "projects",
        [],
    ):

        project_title = project.get(
            "title",
            "",
        )

        project_evidence = project.get(
            "evidence",
            "",
        )

        if not project_evidence:
            continue

        text_chunks = split_into_chunks(
            project_evidence
        )

        for chunk_text in text_chunks:

            chunks.append(
                {
                    "candidate_id": candidate_id,
                    "chunk_id": chunk_id,
                    "chunk_type": "project",
                    "section": "projects",
                    "project_title": project_title,
                    "text": chunk_text,
                }
            )

            chunk_id += 1

    return chunks
from pathlib import Path

from docx import Document
from pypdf import PdfReader


def extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    text_parts = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)

    return "\n".join(text_parts)


def extract_docx(path: Path) -> str:
    document = Document(path)
    text_parts = []

    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            text_parts.append(paragraph.text)

    for table in document.tables:
        for row in table.rows:
            text_parts.append(" | ".join(cell.text for cell in row.cells))

    return "\n".join(text_parts)


def extract_text(path: Path) -> str:
    extension = path.suffix.lower()

    if extension == ".pdf":
        return extract_pdf(path)

    if extension == ".docx":
        return extract_docx(path)

    raise ValueError(f"Unsupported file type: {extension}")
from pathlib import Path

from ingestion.postgresql.extractor import extract_text


RESUME_DIR = Path("data")

pdf_files = [
    path
    for path in RESUME_DIR.iterdir()
    if path.suffix.lower() == ".pdf"
]

for path in pdf_files[:3]:

    print()
    print("=" * 80)
    print(path.name)
    print("=" * 80)

    text = extract_text(path)

    print(text[:5000])
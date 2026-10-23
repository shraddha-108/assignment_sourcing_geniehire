from pathlib import Path

from ingestion.postgresql.extractor import extract_text
from ingestion.postgresql.llm_parser import parse_resume_with_llm


RESUME_DIR = Path("data")


pdf_files = sorted(
    path
    for path in RESUME_DIR.iterdir()
    if path.suffix.lower() == ".pdf"
)


selected_files = pdf_files[5:10]


for path in selected_files:
    print()
    print("=" * 80)
    print(path.name)
    print("=" * 80)

    text = extract_text(path)

    result = parse_resume_with_llm(text)

    print()
    print("NAME:")
    print(result["name"])

    print()
    print("EMAIL:")
    print(result["email"])

    print()
    print("PHONE:")
    print(result["phone"])

    print()
    print("TOTAL EXPERIENCE:")
    print(result["total_experience_months"], "months")

    print()
    print("EXPERIENCES:")

    for experience in result["experiences"]:
        print(
            experience["company"],
            "|",
            experience["title"],
            "|",
            experience["start_date"],
            "to",
            experience["end_date"],
        )

    print()
    print("SKILLS:")

    for skill in result["skills"]:
        print(
            skill["skill"],
            "|",
            skill["total_months"],
            "months",
            "| last used:",
            skill["last_used_date"],
        )

    print()
    print("EVIDENCE SECTIONS:")

    for section, content in result["evidence"].items():
        print()
        print(f"[{section}]")

        if isinstance(content, list):
            for item in content:
                print(item)
        else:
            print(content)
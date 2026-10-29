import argparse
import hashlib
from pathlib import Path

from sqlalchemy import select

from app.database.database import SessionLocal
from app.database.models.resume import Resume


# ==================================================
# Resume directory
# ==================================================

RESUME_DIR = Path("data/new_resumes")


# ==================================================
# Supported resume file types
# ==================================================

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
}


def get_all_resumes() -> list[Path]:
    """
    Get all supported resume files sorted by filename.
    """

    if not RESUME_DIR.exists():
        raise FileNotFoundError(
            f"Resume directory not found: {RESUME_DIR}"
        )

    resumes = sorted(
        [
            file
            for file in RESUME_DIR.iterdir()
            if file.is_file()
            and file.suffix.lower() in SUPPORTED_EXTENSIONS
        ],
        key=lambda file: file.name.lower(),
    )

    return resumes


def calculate_file_hash(file_path: Path) -> str:
    """Hash file contents without importing the heavy embedding stack."""
    digest = hashlib.sha256()
    with file_path.open("rb") as resume_file:
        for chunk in iter(lambda: resume_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filter_already_ingested(
    resumes: list[Path],
    existing_hashes: set[str],
) -> tuple[list[Path], list[Path], list[Path]]:
    """Return new files and exact-content duplicates from the DB or this batch."""
    new_files = []
    database_duplicates = []
    batch_duplicates = []
    seen_hashes = set(existing_hashes)

    for resume_path in resumes:
        file_hash = calculate_file_hash(resume_path)
        if file_hash in existing_hashes:
            database_duplicates.append(resume_path)
        elif file_hash in seen_hashes:
            batch_duplicates.append(resume_path)
        else:
            new_files.append(resume_path)
        seen_hashes.add(file_hash)

    return new_files, database_duplicates, batch_duplicates


def get_existing_hashes() -> set[str]:
    db = SessionLocal()
    try:
        return set(db.scalars(select(Resume.file_hash)).all())
    finally:
        db.close()


def main(dry_run: bool = False):

    all_resumes = get_all_resumes()

    if not all_resumes:
        print(f"No supported resumes found in {RESUME_DIR}.")
        return

    resumes, database_duplicates, batch_duplicates = filter_already_ingested(
        all_resumes,
        get_existing_hashes(),
    )

    print("=" * 70)
    print(f"Folder: {RESUME_DIR}")
    print(f"Supported files: {len(all_resumes)}")
    print(f"Already in database (same SHA-256): {len(database_duplicates)}")
    print(f"Repeated in this folder (same SHA-256): {len(batch_duplicates)}")
    print(f"New files to ingest: {len(resumes)}")
    print("=" * 70)

    for duplicate in database_duplicates:
        print(f"SKIP already ingested: {duplicate.name}")
    for duplicate in batch_duplicates:
        print(f"SKIP duplicate in batch: {duplicate.name}")

    if dry_run:
        print("Dry run complete; no resumes were ingested.")
        return

    if not resumes:
        print("No new resumes to ingest.")
        return

    # Import only after the dry-run and duplicate checks. The pipeline loads
    # the sentence-transformer model, which can take a while during startup.
    from app.ingestion.pipeline import ingest_resume

    successful = []
    failed = []

    for index, resume_path in enumerate(
        resumes,
        start=1,
    ):

        print("\n")
        print("=" * 70)
        print(
            f"PROCESSING RESUME {index}/{len(resumes)}"
        )
        print(
            f"FILE: {resume_path.name}"
        )
        print("=" * 70)

        db = SessionLocal()

        try:

            result = ingest_resume(
                db=db,
                file_path=resume_path,
            )

            successful.append(
                {
                    "file": resume_path.name,
                    "candidate_id": result[
                        "candidate_id"
                    ],
                    "resume_id": result[
                        "resume_id"
                    ],
                    "ingestion_run_id": result[
                        "ingestion_run_id"
                    ],
                    "indexed_evidence_count": result[
                        "indexed_evidence_count"
                    ],
                }
            )

            print(
                f"\nSUCCESS: {resume_path.name}"
            )

        except Exception as exc:

            failed.append(
                {
                    "file": resume_path.name,
                    "error": str(exc),
                }
            )

            print(
                f"\nFAILED: {resume_path.name}"
            )

            print(
                f"ERROR: {exc}"
            )

        finally:

            db.close()

    # ==================================================
    # Final summary
    # ==================================================

    print("\n")
    print("=" * 70)
    print("INGESTION SUMMARY")
    print("=" * 70)

    print(
        f"Total files scanned: {len(all_resumes)}"
    )

    print(
        f"Successful:    {len(successful)}"
    )

    print(
        f"Failed:        {len(failed)}"
    )

    # --------------------------------------------------
    # Successful resumes
    # --------------------------------------------------

    if successful:

        print("\nSUCCESSFUL:")
        print("-" * 70)

        for item in successful:

            print(
                f"{item['file']} | "
                f"candidate_id={item['candidate_id']} | "
                f"resume_id={item['resume_id']} | "
                f"evidence={item['indexed_evidence_count']}"
            )

    # --------------------------------------------------
    # Failed resumes
    # --------------------------------------------------

    if failed:

        print("\nFAILED:")
        print("-" * 70)

        for item in failed:

            print(
                f"{item['file']}\n"
                f"  ERROR: {item['error']}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest new resumes without reprocessing exact duplicates.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show which files would be skipped or ingested.",
    )
    main(dry_run=parser.parse_args().dry_run)

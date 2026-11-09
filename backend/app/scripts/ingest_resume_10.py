import argparse
import hashlib
from pathlib import Path

from sqlalchemy import select

from app.database.database import SessionLocal
from app.database.models.resume import Resume


# ==================================================
# Resume directory
# ==================================================

RESUME_DIR = Path("data/resumes")


# ==================================================
# Batch configuration
# ==================================================

# Only 5 NEW resumes will be ingested per run.
DEFAULT_LIMIT = 5


# ==================================================
# Supported resume file types
# ==================================================

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
}


# ==================================================
# Get all resumes
# ==================================================

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


# ==================================================
# Calculate SHA-256
# ==================================================

def calculate_file_hash(file_path: Path) -> str:
    """
    Calculate SHA-256 hash from the actual file contents.

    This identifies the same resume even if:
    - filename changes
    - file is renamed
    - file is moved
    - file is copied
    """

    digest = hashlib.sha256()

    with file_path.open("rb") as resume_file:
        for chunk in iter(
            lambda: resume_file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


# ==================================================
# Filter already-ingested resumes
# ==================================================

def filter_already_ingested(
    resumes: list[Path],
    existing_hashes: set[str],
) -> tuple[list[Path], list[Path], list[Path]]:
    """
    Separate resumes into:

    1. New files
    2. Files already present in PostgreSQL
    3. Duplicate files inside the current folder

    SHA-256 is used instead of filename.
    """

    new_files = []
    database_duplicates = []
    batch_duplicates = []

    # Start with hashes already stored in PostgreSQL.
    seen_hashes = set(existing_hashes)

    for resume_path in resumes:

        file_hash = calculate_file_hash(resume_path)

        # ----------------------------------------------
        # Already ingested in PostgreSQL
        # ----------------------------------------------

        if file_hash in existing_hashes:

            database_duplicates.append(resume_path)

        # ----------------------------------------------
        # Duplicate inside current folder
        # ----------------------------------------------

        elif file_hash in seen_hashes:

            batch_duplicates.append(resume_path)

        # ----------------------------------------------
        # Completely new resume
        # ----------------------------------------------

        else:

            new_files.append(resume_path)

        # Remember hash so another identical file
        # in this folder is treated as a duplicate.
        seen_hashes.add(file_hash)

    return (
        new_files,
        database_duplicates,
        batch_duplicates,
    )


# ==================================================
# Get hashes already stored in PostgreSQL
# ==================================================

def get_existing_hashes() -> set[str]:
    """
    Get all resume SHA-256 hashes already stored
    in PostgreSQL.
    """

    db = SessionLocal()

    try:

        return set(
            db.scalars(
                select(Resume.file_hash)
            ).all()
        )

    finally:

        db.close()


# ==================================================
# Main ingestion
# ==================================================

def main(
    dry_run: bool = False,
    limit: int = DEFAULT_LIMIT,
):
    """
    Ingest up to `limit` NEW resumes.

    Previously ingested resumes are skipped automatically
    using their SHA-256 hash.
    """

    # ==================================================
    # 1. Find all resumes
    # ==================================================

    all_resumes = get_all_resumes()

    if not all_resumes:

        print(
            f"No supported resumes found in {RESUME_DIR}."
        )

        return

    # ==================================================
    # 2. Check PostgreSQL for already-ingested resumes
    # ==================================================

    existing_hashes = get_existing_hashes()

    (
        new_resumes,
        database_duplicates,
        batch_duplicates,
    ) = filter_already_ingested(
        all_resumes,
        existing_hashes,
    )

    # ==================================================
    # 3. Select ONLY 5 new resumes
    # ==================================================

    resumes_to_ingest = new_resumes[:limit]

    remaining_new = max(
        0,
        len(new_resumes) - len(resumes_to_ingest),
    )

    # ==================================================
    # 4. Print batch information
    # ==================================================

    print("=" * 70)
    print("RESUME INGESTION")
    print("=" * 70)

    print(
        f"Folder:                    {RESUME_DIR}"
    )

    print(
        f"Supported files found:     {len(all_resumes)}"
    )

    print(
        f"Already in database:       {len(database_duplicates)}"
    )

    print(
        f"Duplicates in folder:      {len(batch_duplicates)}"
    )

    print(
        f"New resumes available:     {len(new_resumes)}"
    )

    print(
        f"Batch limit:               {limit}"
    )

    print(
        f"Resumes selected:          {len(resumes_to_ingest)}"
    )

    print(
        f"Remaining for next run:    {remaining_new}"
    )

    print("=" * 70)

    # ==================================================
    # 5. Show already-ingested resumes
    # ==================================================

    if database_duplicates:

        print("\nSKIPPED — ALREADY INGESTED:")
        print("-" * 70)

        for duplicate in database_duplicates:

            print(
                f"SKIP: {duplicate.name}"
            )

    # ==================================================
    # 6. Show duplicate files
    # ==================================================

    if batch_duplicates:

        print("\nSKIPPED — DUPLICATE IN FOLDER:")
        print("-" * 70)

        for duplicate in batch_duplicates:

            print(
                f"SKIP: {duplicate.name}"
            )

    # ==================================================
    # 7. Show selected resumes
    # ==================================================

    if resumes_to_ingest:

        print("\nSELECTED FOR INGESTION:")
        print("-" * 70)

        for index, resume_path in enumerate(
            resumes_to_ingest,
            start=1,
        ):

            print(
                f"{index:02d}. {resume_path.name}"
            )

    # ==================================================
    # 8. Dry run
    # ==================================================

    if dry_run:

        print("\nDry run complete.")

        print(
            "No resumes were ingested."
        )

        return

    # ==================================================
    # 9. Nothing new
    # ==================================================

    if not resumes_to_ingest:

        print(
            "\nNo new resumes to ingest."
        )

        return

    # ==================================================
    # 10. Import ingestion pipeline
    # ==================================================

    # Import only when there are resumes to process.
    # This avoids loading the embedding model unnecessarily.

    from app.ingestion.pipeline import ingest_resume

    successful = []
    failed = []

    # ==================================================
    # 11. Process selected resumes
    # ==================================================

    for index, resume_path in enumerate(
        resumes_to_ingest,
        start=1,
    ):

        print("\n")
        print("=" * 70)

        print(
            f"PROCESSING RESUME "
            f"{index}/{len(resumes_to_ingest)}"
        )

        print(
            f"FILE: {resume_path.name}"
        )

        print("=" * 70)

        db = SessionLocal()

        try:

            # ------------------------------------------
            # Run complete ingestion pipeline
            # ------------------------------------------

            result = ingest_resume(
                db=db,
                file_path=resume_path,
            )

            # ------------------------------------------
            # Record successful ingestion
            # ------------------------------------------

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

            print(
                f"Candidate ID: "
                f"{result['candidate_id']}"
            )

            print(
                f"Resume ID: "
                f"{result['resume_id']}"
            )

            print(
                f"Evidence indexed: "
                f"{result['indexed_evidence_count']}"
            )

        except Exception as exc:

            # ------------------------------------------
            # Record failure and continue
            # ------------------------------------------

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
    # 12. Final summary
    # ==================================================

    print("\n")
    print("=" * 70)
    print("INGESTION SUMMARY")
    print("=" * 70)

    print(
        f"Total files scanned:       {len(all_resumes)}"
    )

    print(
        f"Already in database:       {len(database_duplicates)}"
    )

    print(
        f"Duplicate in folder:       {len(batch_duplicates)}"
    )

    print(
        f"New resumes available:     {len(new_resumes)}"
    )

    print(
        f"Selected this run:         {len(resumes_to_ingest)}"
    )

    print(
        f"Successful:                {len(successful)}"
    )

    print(
        f"Failed:                    {len(failed)}"
    )

    print(
        f"Remaining for next run:    {remaining_new}"
    )

    # ==================================================
    # 13. Successful resumes
    # ==================================================

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

    # ==================================================
    # 14. Failed resumes
    # ==================================================

    if failed:

        print("\nFAILED:")
        print("-" * 70)

        for item in failed:

            print(
                f"{item['file']}\n"
                f"  ERROR: {item['error']}"
            )

    # ==================================================
    # 15. Next batch information
    # ==================================================

    if remaining_new > 0:

        print("\n")

        print(
            f"{remaining_new} new resumes are still "
            f"waiting for the next run."
        )

        print(
            "Run the script again to process the next "
            "batch of 5."
        )

    else:

        print("\n")

        print(
            "No additional new resumes are waiting."
        )


# ==================================================
# CLI
# ==================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Ingest new resumes in batches of 5 while "
            "skipping previously ingested resumes."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=(
            "Maximum number of NEW resumes to ingest "
            f"(default: {DEFAULT_LIMIT})."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Show which resumes would be skipped "
            "and ingested without actually ingesting them."
        ),
    )

    args = parser.parse_args()

    if args.limit <= 0:

        parser.error(
            "--limit must be greater than 0."
        )

    main(
        dry_run=args.dry_run,
        limit=args.limit,
    )
from pathlib import Path
from datetime import datetime

from sqlalchemy.orm import Session

from app.database.models.ingestion_run import IngestionRun

from app.ingestion.extractor import extract_text
from app.ingestion.parser import parse_resume
from app.ingestion.normalizer import normalize_resume
from app.ingestion.validator import validate_resume
from app.ingestion.service import persist_candidate

from app.ingestion.vector.index_service import (
    index_candidate_evidence,
    delete_candidate_evidence,
)

from app.storage.s3_resume import (
    build_resume_storage_key,
    upload_resume,
    delete_resume,
)


def ingest_resume(
    db: Session,
    file_path: str | Path,
) -> dict:
    """
    Run the complete resume ingestion pipeline.

    Flow:

        Local resume
            ↓
        SHA-256 hash
            ↓
        S3 upload
            ↓
        Text extraction
            ↓
        LLM parsing
            ↓
        Normalization
            ↓
        Validation
            ↓
        PostgreSQL
            ↓
        Candidate evidence
            ↓
        Qdrant indexing
            ↓
        Completed

    The PostgreSQL resume.storage_key always contains
    the S3 object key, never the local filesystem path.
    """

    file_path = Path(file_path)

    # ==================================================
    # 0. Validate local file
    # ==================================================

    if not file_path.exists():
        raise FileNotFoundError(
            f"Resume file not found: {file_path}"
        )

    if not file_path.is_file():
        raise ValueError(
            f"Path is not a file: {file_path}"
        )

    # ==================================================
    # 1. Calculate file hash
    # ==================================================

    print("\n[1/8] Calculating file hash...")

    file_hash = calculate_file_hash(
        file_path
    )

    print(
        f"      SHA-256: {file_hash}"
    )

    # ==================================================
    # 2. Upload resume to S3
    # ==================================================

    storage_key = build_resume_storage_key(
        file_hash=file_hash,
        filename=file_path.name,
    )

    print("[2/8] Uploading resume to S3...")

    upload_resume(
        file_path=file_path,
        storage_key=storage_key,
    )

    print(
        f"      S3 key: {storage_key}"
    )

    # ==================================================
    # 3. Extract
    # ==================================================

    print("[3/8] Extracting resume text...")

    try:

        text = extract_text(
            file_path
        )

        if not text or not text.strip():
            raise ValueError(
                "Resume extraction returned empty text."
            )

        print(
            f"      Extracted {len(text)} characters."
        )

    except Exception:

        # Extraction failed after S3 upload.
        # Remove the uploaded object so S3 does not
        # contain a resume that was never ingested.

        try:
            delete_resume(storage_key)
        except Exception:
            pass

        raise

    # ==================================================
    # 4. Parse
    # ==================================================

    print("[4/8] Parsing resume with LLM...")

    try:

        resume_data = parse_resume(
            text
        )

        print(
            f"      Candidate: "
            f"{resume_data.candidate.name}"
        )

    except Exception:

        try:
            delete_resume(storage_key)
        except Exception:
            pass

        raise

    # ==================================================
    # 5. Normalize
    # ==================================================

    print("[5/8] Normalizing resume data...")

    resume_data = normalize_resume(
        resume_data
    )

    print(
        "      Normalization completed."
    )

    # ==================================================
    # 6. Validate
    # ==================================================

    print("[6/8] Validating resume data...")

    try:

        validate_resume(
            resume_data
        )

        print(
            "      Validation passed."
        )

    except Exception:

        try:
            delete_resume(storage_key)
        except Exception:
            pass

        raise

    # ==================================================
    # 7. PostgreSQL
    # ==================================================

    print(
        "[7/8] Persisting resume to PostgreSQL..."
    )

    try:

        candidate = persist_candidate(
            db=db,
            resume_data=resume_data,
            filename=file_path.name,

            # IMPORTANT:
            # Store S3 key, NOT local file path.
            storage_key=storage_key,

            file_hash=file_hash,
            file_type=file_path.suffix.lower(),
            file_size=file_path.stat().st_size,
        )

        print(
            f"      Candidate ID: {candidate.id}"
        )

        resume = candidate.resumes[-1]

        ingestion_run = IngestionRun(
            resume_id=resume.id,
            status="INDEXING",
            current_stage="QDRANT_INDEXING",
            started_at=datetime.utcnow(),
        )

        db.add(ingestion_run)
        db.commit()
        db.refresh(ingestion_run)

    except Exception:

        db.rollback()

        try:
            delete_resume(storage_key)
        except Exception:
            pass

        raise

    # ==================================================
    # 8. Qdrant
    # ==================================================

    print(
        "[8/8] Indexing evidence into Qdrant..."
    )

    try:

        indexed_count = index_candidate_evidence(
            db=db,
            candidate_id=candidate.id,
        )

        ingestion_run.status = "COMPLETED"
        ingestion_run.current_stage = "COMPLETED"
        ingestion_run.completed_at = datetime.utcnow()

        db.commit()

        print(
            f"      Indexed {indexed_count} evidence records."
        )

        print(
            "[DONE] Ingestion completed successfully."
        )

        return {
            "candidate_id": candidate.id,
            "resume_id": resume.id,
            "ingestion_run_id": ingestion_run.id,
            "storage_key": storage_key,
            "indexed_evidence_count": indexed_count,
            "status": "COMPLETED",
        }

    except Exception as exc:

        # Mark ingestion as failed.
        ingestion_run.status = "FAILED"
        ingestion_run.current_stage = "QDRANT_INDEXING"
        ingestion_run.error_message = str(exc)
        ingestion_run.completed_at = datetime.utcnow()

        db.commit()

        # Remove Qdrant points created for this candidate.
        try:
            delete_candidate_evidence(
                candidate_id=candidate.id
            )
        except Exception:
            pass

        # Remove PostgreSQL records created for this
        # candidate.
        #
        # This assumes your reset/re-ingestion workflow
        # is operating on a clean database and that
        # cascading relationships are configured.
        #
        # If you want transactional rollback of the
        # complete candidate tree, we should refactor
        # persist_candidate to avoid its internal commit.
        #
        # For now we keep the failed ingestion visible
        # through ingestion_run.

        raise


def calculate_file_hash(
    file_path: Path,
) -> str:
    """
    Calculate SHA-256 hash of the resume file.
    """

    import hashlib

    sha256 = hashlib.sha256()

    with file_path.open(
        "rb"
    ) as file:

        while True:

            chunk = file.read(
                1024 * 1024
            )

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()
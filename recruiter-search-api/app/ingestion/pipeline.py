from pathlib import Path
from datetime import datetime

from sqlalchemy.orm import Session

from app.database.models.ingestion_run import IngestionRun

from app.ingestion.extractor import extract_text
from app.ingestion.parser import parse_resume
from app.ingestion.normalizer import normalize_resume
from app.ingestion.validator import validate_resume
from app.ingestion.service import persist_candidate

from app.ingestion.vector.index_service import index_candidate_evidence


def ingest_resume(
    db: Session,
    file_path: str | Path,
) -> dict:
    """
    Run the complete resume ingestion pipeline.

    Current flow:

        Local resume
            ↓
        Extraction
            ↓
        LLM parsing
            ↓
        Normalization
            ↓
        Validation
            ↓
        PostgreSQL
            ↓
        Qdrant indexing
            ↓
        Completed

    Returns basic ingestion information.
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Resume file not found: {file_path}"
        )

    if not file_path.is_file():
        raise ValueError(
            f"Path is not a file: {file_path}"
        )

    # --------------------------------------------------
    # 1. EXTRACT
    # --------------------------------------------------

    print("\n[1/7] Extracting resume text...")

    text = extract_text(file_path)

    if not text or not text.strip():
        raise ValueError(
            "Resume extraction returned empty text."
        )

    print(
        f"      Extracted {len(text)} characters."
    )

    # --------------------------------------------------
    # 2. PARSE
    # --------------------------------------------------

    print("[2/7] Parsing resume with LLM...")

    resume_data = parse_resume(text)

    print(
        f"      Candidate: {resume_data.candidate.name}"
    )

    # --------------------------------------------------
    # 3. NORMALIZE
    # --------------------------------------------------

    print("[3/7] Normalizing resume data...")

    resume_data = normalize_resume(
        resume_data
    )

    print(
        "      Normalization completed."
    )

    # --------------------------------------------------
    # 4. VALIDATE
    # --------------------------------------------------

    print("[4/7] Validating resume data...")

    validate_resume(
        resume_data
    )

    print(
        "      Validation passed."
    )

    # --------------------------------------------------
    # 5. PERSIST TO POSTGRESQL
    # --------------------------------------------------

    print("[5/7] Persisting resume to PostgreSQL...")

    file_hash = calculate_file_hash(
        file_path
    )

    candidate = persist_candidate(
        db=db,
        resume_data=resume_data,
        filename=file_path.name,
        storage_key=str(file_path),
        file_hash=file_hash,
        file_type=file_path.suffix.lower(),
        file_size=file_path.stat().st_size,
    )

    print(
        f"      Candidate ID: {candidate.id}"
    )

    # --------------------------------------------------
    # Create ingestion run
    #
    # We create it here because the current schema
    # requires resume_id.
    # --------------------------------------------------

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

    # --------------------------------------------------
    # 6. INDEX EVIDENCE INTO QDRANT
    # --------------------------------------------------

    print("[6/7] Indexing evidence into Qdrant...")

    try:

        indexed_count = index_candidate_evidence(
            db=db,
            candidate_id=candidate.id,
        )

        print(
            f"      Indexed {indexed_count} evidence records."
        )

    except Exception as exc:

        ingestion_run.status = "FAILED"
        ingestion_run.current_stage = "QDRANT_INDEXING"
        ingestion_run.error_message = str(exc)
        ingestion_run.completed_at = datetime.utcnow()

        db.commit()

        raise

    # --------------------------------------------------
    # 7. COMPLETE
    # --------------------------------------------------

    ingestion_run.status = "COMPLETED"
    ingestion_run.current_stage = "COMPLETED"
    ingestion_run.completed_at = datetime.utcnow()

    db.commit()

    print("[7/7] Ingestion completed successfully.")

    return {
        "candidate_id": candidate.id,
        "resume_id": resume.id,
        "ingestion_run_id": ingestion_run.id,
        "indexed_evidence_count": indexed_count,
        "status": "COMPLETED",
    }


def calculate_file_hash(
    file_path: Path,
) -> str:
    """
    Calculate SHA-256 hash of the resume file.

    Used by the resumes table to uniquely identify
    the uploaded file.
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
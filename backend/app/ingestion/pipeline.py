
from pathlib import Path
from datetime import datetime

from sqlalchemy.orm import Session

from app.database.models.ingestion_run import IngestionRun

from app.ingestion.extractor import extract_text

from app.ingestion.classification_input_builder import (
    build_classification_input,
)

from app.ingestion.classifier import (
    classify_resume,
    CLASSIFICATION_VERSION,
)

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
        Classification input preparation
            ↓
        Resume domain classification (GPT-6 Luna)
            ↓
        Domain-guided resume extraction (GPT-6 Luna)
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
    # 3. Extract complete resume text
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
        # Remove the uploaded object.

        try:
            delete_resume(storage_key)
        except Exception:
            pass

        raise

    # ==================================================
    # 4. Classification + Detailed Parsing
    # ==================================================

    try:

        # ----------------------------------------------
        # 4A. Build classification input
        # ----------------------------------------------

        print(
            "[4A] Preparing classification input..."
        )

        classification_text = build_classification_input(
            text
        )

        if not classification_text.strip():
            raise ValueError(
                "Classification input is empty."
            )

        print(
            f"      Classification input: "
            f"{len(classification_text)} characters."
        )

        # ----------------------------------------------
        # 4B. Classify resume
        # ----------------------------------------------

        print(
            "[4B] Classifying resume with GPT-6 Luna..."
        )

        classification = classify_resume(
            classification_text
        )

        primary_domain = (
            classification.primary_domain.value
        )

        domain_confidence = (
            classification.confidence
        )

        print(
            f"      Primary domain: {primary_domain}"
        )

        print(
            f"      Confidence: {domain_confidence:.2f}"
        )

        # ----------------------------------------------
        # 4C. Detailed resume extraction
        # ----------------------------------------------

        print(
            "[4C] Parsing complete resume with GPT-6 Luna..."
        )

        # IMPORTANT:
        # Send the COMPLETE raw resume text.
        # Only the domain-specific guidance changes.

        resume_data = parse_resume(
            text,
            primary_domain=primary_domain,
        )

        print(
            f"      Candidate: "
            f"{resume_data.candidate.name}"
        )

    except Exception:

        # Classification or parsing failed.
        # Remove the uploaded S3 object.

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

            # Resume classification metadata
            primary_domain=primary_domain,
            domain_confidence=domain_confidence,
            classification_version=CLASSIFICATION_VERSION,
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
            "primary_domain": primary_domain,
            "domain_confidence": domain_confidence,
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

        # Existing PostgreSQL cleanup behaviour is preserved.
        # A future transaction refactor can make this atomic.

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

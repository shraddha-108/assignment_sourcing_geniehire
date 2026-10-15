import hashlib
from pathlib import Path

from database import SessionLocal
from ingestion.postgresql.extractor import extract_text
from ingestion.postgresql.parser import parse_resume
from ingestion.postgresql.repository import (
    candidate_exists,
    create_candidate,
)
from ingestion.vectorDB.chunker import create_chunks
from ingestion.vectorDB.embedder import embed_text
from ingestion.vectorDB.qdrant_client import upsert_evidence


BASE_DIR = Path(__file__).resolve().parents[2]
RESUME_DIR = BASE_DIR / "data"


def calculate_file_hash(path: Path) -> str:
    sha256 = hashlib.sha256()

    with open(path, "rb") as file:
        while chunk := file.read(1024 * 1024):
            sha256.update(chunk)

    return sha256.hexdigest()


def process_resume(path: Path) -> None:
    print(f"Processing: {path.name}")

    resume_hash = calculate_file_hash(path)

    db = SessionLocal()

    try:
        text = extract_text(path)

        if not text.strip():
            print("No text extracted. Skipping.")
            return

        if candidate_exists(db, resume_hash):
            print("Already exists. Skipping.")
            return

        candidate_data = parse_resume(
            text=text,
            filename=path.name,
        )

        candidate = create_candidate(
            db=db,
            candidate_data=candidate_data,
            resume_filename=path.name,
            resume_hash=resume_hash,
        )

        print(
            f"Saved candidate: "
            f"{candidate.name} "
            f"(ID: {candidate.id})"
        )

        print(
            f"  Skills: "
            f"{len(candidate_data['skills'])}"
        )

        print(
            f"  Experiences: "
            f"{len(candidate_data['experiences'])}"
        )

        chunks = create_chunks(
            candidate_id=candidate.id,
            text=text,
        )

        print(
            f"  Vector chunks: "
            f"{len(chunks)}"
        )

        for chunk in chunks:

            vector = embed_text(
                chunk["text"]
            )

            upsert_evidence(
                candidate_id=chunk["candidate_id"],
                chunk_id=chunk["chunk_id"],
                chunk_type=chunk["chunk_type"],
                section=chunk["section"],
                text=chunk["text"],
                vector=vector,
            )

        print(
            "  Vector ingestion complete."
        )

    except Exception as error:
        db.rollback()

        print(
            f"Failed: {path.name}"
        )

        print(error)

    finally:
        db.close()


def run_pipeline() -> None:

    if not RESUME_DIR.exists():
        raise FileNotFoundError(
            f"Resume directory not found: "
            f"{RESUME_DIR}"
        )

    files = [
        path
        for path in RESUME_DIR.iterdir()
        if path.suffix.lower()
        in {".pdf", ".docx"}
    ]

    print(
        f"Found {len(files)} resumes."
    )

    for path in files:
        process_resume(path)


if __name__ == "__main__":
    run_pipeline()
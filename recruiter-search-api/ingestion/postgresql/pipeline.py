import hashlib
from pathlib import Path

from database import SessionLocal
from ingestion.postgresql.extractor import extract_text
from ingestion.postgresql.llm_parser import parse_resume_with_llm
from ingestion.postgresql.repository import create_candidate
from ingestion.storage.s3_client import (
    upload_resume,
    resume_exists,
)
from ingestion.vectorDB.chunker import create_chunks
from ingestion.vectorDB.embedder import embed_text
from ingestion.vectorDB.qdrant_client import (
    COLLECTION_NAME,
    client,
    upsert_evidence,
)
from models import Candidate

from qdrant_client import models


BASE_DIR = Path(__file__).resolve().parents[2]
RESUME_DIR = BASE_DIR / "data"

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
}


def calculate_file_hash(
    path: Path,
) -> str:

    sha256 = hashlib.sha256()

    with open(
        path,
        "rb",
    ) as file:

        while chunk := file.read(
            1024 * 1024
        ):
            sha256.update(chunk)

    return sha256.hexdigest()


def build_storage_key(
    candidate_id: int,
    resume_hash: str,
    path: Path,
) -> str:

    return (
        f"resumes/"
        f"{candidate_id}/"
        f"{resume_hash}"
        f"{path.suffix.lower()}"
    )


def remove_stale_qdrant_chunks(
    candidate_id: int,
    current_chunk_ids: set[int],
) -> int:
    """
    Remove old Qdrant evidence chunks for a candidate
    that are no longer present in the current indexing run.

    This is intentionally performed only after the new
    chunks have been successfully uploaded.
    """

    if not current_chunk_ids:
        return 0

    if not client.collection_exists(
        COLLECTION_NAME
    ):
        return 0

    scroll_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="candidate_id",
                match=models.MatchValue(
                    value=candidate_id,
                ),
            )
        ]
    )

    stale_point_ids = []

    offset = None

    while True:

        points, next_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=scroll_filter,
            limit=100,
            offset=offset,
            with_payload=[
                "candidate_id",
                "chunk_id",
            ],
            with_vectors=False,
        )

        for point in points:

            payload = point.payload or {}

            chunk_id = payload.get(
                "chunk_id"
            )

            if (
                chunk_id is None
                or int(chunk_id)
                not in current_chunk_ids
            ):
                stale_point_ids.append(
                    point.id
                )

        if next_offset is None:
            break

        offset = next_offset

    if not stale_point_ids:
        return 0

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=models.PointIdsList(
            points=stale_point_ids,
        ),
    )

    return len(stale_point_ids)


def process_resume(
    path: Path,
) -> None:

    print()
    print("=" * 70)
    print(
        f"Processing: {path.name}"
    )
    print("=" * 70)

    resume_hash = calculate_file_hash(
        path
    )

    db = SessionLocal()

    try:

        print(
            "1. Extracting text..."
        )

        text = extract_text(
            path
        )

        if not text.strip():

            print(
                "No text extracted. Skipping."
            )

            return

        print(
            f"   Extracted {len(text)} characters."
        )

        print(
            "2. Parsing resume with LLM..."
        )

        candidate_data = (
            parse_resume_with_llm(
                text=text,
            )
        )

        print(
            f"   Name: {candidate_data['name']}"
        )

        print(
            f"   Email: {candidate_data['email']}"
        )

        print(
            f"   Phone: {candidate_data['phone']}"
        )

        print(
            "   Total experience: "
            f"{candidate_data['total_experience_months']} months"
        )

        print(
            "   Experiences: "
            f"{len(candidate_data['experiences'])}"
        )

        print(
            "   Skills: "
            f"{len(candidate_data['skills'])}"
        )

        print(
            "3. Checking for duplicate resume..."
        )

        candidate = (
            db.query(Candidate)
            .filter(
                Candidate.resume_hash
                == resume_hash
            )
            .first()
        )

        if candidate:

            print(
                "   Existing candidate found: "
                f"{candidate.name} "
                f"(ID: {candidate.id})"
            )

        else:

            print(
                "   New resume. Creating candidate..."
            )

            candidate = create_candidate(
                db=db,
                candidate_data=candidate_data,
                resume_filename=path.name,
                resume_hash=resume_hash,
            )

            print(
                "   Candidate created: "
                f"{candidate.name} "
                f"(ID: {candidate.id})"
            )

        print(
            "4. Candidate details:"
        )

        print(
            "   Total experience: "
            f"{candidate.total_experience_months} months"
        )

        for experience in candidate_data[
            "experiences"
        ]:

            print(
                "   Experience: "
                f"{experience.get('company')} | "
                f"{experience.get('title')} | "
                f"{experience.get('start_date')} "
                f"to "
                f"{experience.get('end_date')}"
            )

        for skill in candidate_data[
            "skills"
        ]:

            print(
                "   Skill: "
                f"{skill['skill']} | "
                f"{skill['total_months']} months | "
                f"last used: "
                f"{skill['last_used_date']}"
            )

        storage_key = build_storage_key(
            candidate_id=candidate.id,
            resume_hash=resume_hash,
            path=path,
        )

        print(
            "5. S3 storage..."
        )

        existing_storage_key = (
            candidate.resume_storage_key
        )

        if (
            existing_storage_key
            and resume_exists(
                existing_storage_key
            )
        ):

            print(
                "   Resume already exists in S3:"
            )

            print(
                f"   {existing_storage_key}"
            )

        else:

            upload_resume(
                file_path=str(path),
                storage_key=storage_key,
            )

            candidate.resume_storage_key = (
                storage_key
            )

            db.commit()
            db.refresh(candidate)

            print(
                "   Uploaded to S3: "
                f"{storage_key}"
            )

        print(
            "6. Creating vector chunks..."
        )

        chunks = create_chunks(
            candidate_id=candidate.id,
            candidate_data=candidate_data,
        )

        print(
            f"   Created {len(chunks)} chunks."
        )

        if not chunks:

            print(
                "   No vector chunks generated."
            )

        print(
            "7. Embedding and Qdrant ingestion..."
        )

        for index, chunk in enumerate(
            chunks,
            start=1,
        ):

            vector = embed_text(
                chunk["text"]
            )

            metadata = {
                "company": chunk.get(
                    "company"
                ),
                "job_title": chunk.get(
                    "job_title"
                ),
                "start_date": chunk.get(
                    "start_date"
                ),
                "end_date": chunk.get(
                    "end_date"
                ),
                "project_title": chunk.get(
                    "project_title"
                ),
            }

            upsert_evidence(
                candidate_id=chunk[
                    "candidate_id"
                ],
                chunk_id=chunk[
                    "chunk_id"
                ],
                chunk_type=chunk[
                    "chunk_type"
                ],
                section=chunk[
                    "section"
                ],
                text=chunk[
                    "text"
                ],
                vector=vector,
                metadata=metadata,
            )

            print(
                f"   Vector {index}/{len(chunks)} "
                "uploaded."
            )

        # -----------------------------------------------------
        # Remove stale evidence only AFTER all current chunks
        # have been successfully uploaded.
        # -----------------------------------------------------

        current_chunk_ids = {
            int(chunk["chunk_id"])
            for chunk in chunks
        }

        stale_count = (
            remove_stale_qdrant_chunks(
                candidate_id=candidate.id,
                current_chunk_ids=current_chunk_ids,
            )
        )

        if stale_count:

            print(
                "   Removed "
                f"{stale_count} stale Qdrant chunks."
            )

        else:

            print(
                "   No stale Qdrant chunks found."
            )

        print()
        print(
            f"SUCCESS: {path.name}"
        )

        print(
            f"Candidate ID: {candidate.id}"
        )

    except Exception as error:

        db.rollback()

        print()
        print(
            f"FAILED: {path.name}"
        )

        print(
            f"Error: {error}"
        )

    finally:

        db.close()


def run_pipeline() -> None:

    if not RESUME_DIR.exists():

        raise FileNotFoundError(
            "Resume directory not found: "
            f"{RESUME_DIR}"
        )

    files = sorted(
        path
        for path in RESUME_DIR.iterdir()
        if (
            path.is_file()
            and path.suffix.lower()
            in SUPPORTED_EXTENSIONS
        )
    )

    print(
        f"Found {len(files)} resumes."
    )

    if not files:

        print(
            "No PDF or DOCX resumes found."
        )

        return

    for path in files:
        process_resume(path)


if __name__ == "__main__":
    run_pipeline()
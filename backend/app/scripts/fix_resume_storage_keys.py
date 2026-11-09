"""Repair resume database pointers by matching stored file hashes to S3 keys.

Runs in dry-run mode by default. Pass ``--apply`` to update PostgreSQL.
No S3 objects are uploaded, renamed, or deleted.
"""

import os
import sys
from collections import defaultdict

import boto3
from dotenv import load_dotenv
from sqlalchemy import select

from app.database.database import SessionLocal
from app.database.models.resume import Resume


load_dotenv(override=True)

BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION")

if not BUCKET_NAME:
    raise RuntimeError("S3_BUCKET_NAME is not configured")

s3 = boto3.client("s3", region_name=AWS_REGION)


def list_resume_objects() -> list[str]:
    """Return existing object keys under the private resumes/ prefix."""
    keys = []
    continuation_token = None
    while True:
        request = {"Bucket": BUCKET_NAME, "Prefix": "resumes/"}
        if continuation_token:
            request["ContinuationToken"] = continuation_token
        response = s3.list_objects_v2(**request)
        keys.extend(
            item["Key"]
            for item in response.get("Contents", [])
            if not item["Key"].endswith("/")
        )
        if not response.get("IsTruncated"):
            return keys
        continuation_token = response["NextContinuationToken"]


def key_hash(key: str) -> str | None:
    filename = key.rsplit("/", 1)[-1]
    digest = filename.rsplit(".", 1)[0].casefold()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        return None
    return digest


def main() -> None:
    apply_changes = "--apply" in sys.argv[1:]
    keys_by_hash = defaultdict(list)
    for key in list_resume_objects():
        digest = key_hash(key)
        if digest:
            keys_by_hash[digest].append(key)

    db = SessionLocal()
    try:
        resumes = db.scalars(select(Resume).order_by(Resume.id)).all()
        updates = []
        missing = 0
        already_correct = 0
        duplicate_object_hashes = 0

        for resume in resumes:
            matches = sorted(set(keys_by_hash.get(resume.file_hash.casefold(), [])))
            if not matches:
                missing += 1
                continue
            if len(matches) > 1:
                duplicate_object_hashes += 1

            # Matching SHA-256 hashes identify identical file contents. Keep
            # the current key when it is one of those verified copies.
            target_key = resume.storage_key if resume.storage_key in matches else matches[0]
            if target_key == resume.storage_key:
                already_correct += 1
                continue
            updates.append((resume, target_key))

        print(
            f"Mode: {'APPLY' if apply_changes else 'DRY RUN'} | "
            f"resume rows: {len(resumes)} | verified updates: {len(updates)} | "
            f"already correct: {already_correct} | no exact object: {missing} | "
            f"duplicate hashes: {duplicate_object_hashes}"
        )
        for resume, target_key in updates[:10]:
            print(
                f"candidate={resume.candidate_id} resume={resume.id} "
                f"filename={resume.filename} -> {target_key}"
            )

        if apply_changes:
            for resume, target_key in updates:
                resume.storage_key = target_key
            db.commit()
            print(f"Updated {len(updates)} resume storage pointers.")
        else:
            db.rollback()
            print("No database changes made. Re-run with --apply to apply verified mappings.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

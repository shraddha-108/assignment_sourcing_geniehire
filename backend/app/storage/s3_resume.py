import mimetypes
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv


load_dotenv(override=True)


def get_s3_client():
    region = os.getenv("AWS_REGION")

    return boto3.client(
        "s3",
        region_name=region,
    )


def get_bucket_name() -> str:
    bucket_name = os.getenv("S3_BUCKET_NAME")

    if not bucket_name:
        raise RuntimeError(
            "S3_BUCKET_NAME is not configured."
        )

    return bucket_name


def build_resume_storage_key(
    file_hash: str,
    filename: str,
) -> str:
    """
    Build a stable S3 object key for a resume.

    The SHA-256 file hash makes the object key independent
    of the local Windows/Linux filesystem path.
    """

    extension = Path(filename).suffix.lower()

    if not extension:
        raise ValueError(
            "Resume filename must have a file extension."
        )

    return f"resumes/{file_hash}{extension}"


def upload_resume(
    file_path: str | Path,
    storage_key: str,
) -> str:
    """
    Upload a resume to the private S3 bucket.

    Returns the exact S3 object key.
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

    bucket_name = get_bucket_name()
    s3 = get_s3_client()

    content_type = (
        mimetypes.guess_type(file_path.name)[0]
        or "application/octet-stream"
    )

    s3.upload_file(
        Filename=str(file_path),
        Bucket=bucket_name,
        Key=storage_key,
        ExtraArgs={
            "ContentType": content_type,
        },
    )

    return storage_key


def delete_resume(
    storage_key: str,
) -> None:
    """
    Delete a resume object from S3.

    Used for cleanup when ingestion fails after upload.
    """

    bucket_name = get_bucket_name()
    s3 = get_s3_client()

    s3.delete_object(
        Bucket=bucket_name,
        Key=storage_key,
    )


def generate_resume_presigned_url(
    storage_key: str,
) -> str:
    """
    Generate a temporary inline-read URL
    for an existing private S3 object.
    """

    if not storage_key:
        raise ValueError(
            "Resume storage key cannot be empty."
        )

    bucket_name = get_bucket_name()
    s3 = get_s3_client()

    return s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": bucket_name,
            "Key": storage_key,
            "ResponseContentDisposition": "inline",
        },
        ExpiresIn=3600,
    )
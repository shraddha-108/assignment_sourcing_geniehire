import os

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "geniehire-resumes")
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
)


def upload_resume(
    file_path: str,
    storage_key: str,
) -> str:
    s3_client.upload_file(
        file_path,
        BUCKET_NAME,
        storage_key,
    )

    return storage_key


def resume_exists(storage_key: str) -> bool:
    try:
        s3_client.head_object(
            Bucket=BUCKET_NAME,
            Key=storage_key,
        )
        return True

    except ClientError as error:
        error_code = error.response.get(
            "Error",
            {},
        ).get(
            "Code"
        )

        if error_code in {
            "404",
            "NoSuchKey",
            "NotFound",
        }:
            return False

        raise
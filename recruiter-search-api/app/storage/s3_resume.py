import os

from dotenv import load_dotenv


load_dotenv(override=True)


def generate_resume_presigned_url(storage_key: str) -> str:
    """Generate a temporary inline-read URL for an existing private S3 object."""
    bucket_name = os.getenv("S3_BUCKET_NAME")

    if not bucket_name:
        raise RuntimeError("S3_BUCKET_NAME is not configured.")

    import boto3

    region = os.getenv("AWS_REGION")
    s3 = boto3.client("s3", region_name=region)

    return s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": bucket_name,
            "Key": storage_key,
            "ResponseContentType": "application/pdf",
            "ResponseContentDisposition": "inline",
        },
        ExpiresIn=3600,
    )
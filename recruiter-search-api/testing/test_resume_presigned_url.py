import sys
from types import SimpleNamespace

from app.storage import s3_resume


class FakeS3Client:
    def __init__(self):
        self.calls = []

    def generate_presigned_url(self, **kwargs):
        self.calls.append(kwargs)
        return f"https://private.example/{len(self.calls)}"


def test_generates_a_fresh_one_hour_get_url_for_existing_key(monkeypatch):
    fake_client = FakeS3Client()
    monkeypatch.setenv("S3_BUCKET_NAME", "private-resumes")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(
        client=lambda service, region_name: fake_client
    ))

    key = "candidate-resumes/123/resume.pdf"
    first_url = s3_resume.generate_resume_presigned_url(key)
    second_url = s3_resume.generate_resume_presigned_url(key)

    assert first_url != second_url
    assert len(fake_client.calls) == 2
    assert all(call["ClientMethod"] == "get_object" for call in fake_client.calls)
    assert all(call["Params"] == {"Bucket": "private-resumes", "Key": key}
        for call in fake_client.calls)
    assert all(call["ExpiresIn"] == 3600 for call in fake_client.calls)

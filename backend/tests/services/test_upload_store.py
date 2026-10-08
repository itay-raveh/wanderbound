from typing import Any
from urllib.parse import parse_qs, urlsplit

import boto3
import pytest
from botocore.config import Config
from botocore.stub import Stubber

from app.services.upload_store import UploadStoreError, UploadStoreService

FAKE_KEY = "test-value"


def _client(endpoint: str) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="garage",
        aws_access_key_id="access",
        aws_secret_access_key=FAKE_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@pytest.fixture
def store() -> UploadStoreService:
    internal = _client("http://internal:3900")
    signing = _client("http://public:3900")
    return UploadStoreService(internal, signing, bucket="uploads", presign_ttl=900)


def test_signed_part_targets_public_storage_and_binds_the_requested_upload(
    store: UploadStoreService,
) -> None:
    url = urlsplit(store.sign_part("uploads/id.zip", "provider-id", 3, 1_024))
    params = parse_qs(url.query)

    assert url.netloc == "public:3900"
    assert url.path == "/uploads/uploads/id.zip"
    assert params["uploadId"] == ["provider-id"]
    assert params["partNumber"] == ["3"]
    assert "content-length" in params["X-Amz-SignedHeaders"][0].split(";")


def test_provider_errors_are_normalized_without_provider_text_or_url(
    store: UploadStoreService,
) -> None:
    with Stubber(store.internal_client) as stubber:
        stubber.add_client_error(
            "head_object",
            service_error_code="InternalError",
            service_message="provider exploded https://secret.invalid/signed",
        )
        with pytest.raises(UploadStoreError) as caught:
            store.head("uploads/id.zip")
    assert str(caught.value) == "upload store operation failed"
    assert caught.value.code == "InternalError"
    assert "provider exploded" not in str(caught.value)
    assert "https://" not in str(caught.value)

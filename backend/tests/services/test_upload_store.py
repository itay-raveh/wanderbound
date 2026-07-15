from typing import Any
from unittest.mock import MagicMock

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


def test_sign_uses_public_client_and_requested_part(store: UploadStoreService) -> None:
    signing = MagicMock()
    signing.generate_presigned_url.return_value = "https://public.example/signed"
    store.signing_client = signing

    assert (
        store.sign_part("uploads/id.zip", "provider-id", 3, 1_024)
        == "https://public.example/signed"
    )
    signing.generate_presigned_url.assert_called_once_with(
        "upload_part",
        Params={
            "Bucket": "uploads",
            "Key": "uploads/id.zip",
            "UploadId": "provider-id",
            "PartNumber": 3,
            "ContentLength": 1_024,
        },
        ExpiresIn=900,
        HttpMethod="PUT",
    )


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

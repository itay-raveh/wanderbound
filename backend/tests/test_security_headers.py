from typing import TYPE_CHECKING

from pydantic import AnyHttpUrl

from app.core.config import get_settings
from app.frontend import _content_security_policy

if TYPE_CHECKING:
    import pytest


def test_csp_allows_virtual_hosted_uploads(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "UPLOAD_S3_PUBLIC_ENDPOINT_URL",
        AnyHttpUrl("https://fsn1.your-objectstorage.com"),
    )
    monkeypatch.setattr(settings, "UPLOAD_S3_BUCKET", "wanderbound-uploads")
    monkeypatch.setattr(settings, "UPLOAD_S3_ADDRESSING_STYLE", "virtual")

    assert (
        "https://wanderbound-uploads.fsn1.your-objectstorage.com"
        in _content_security_policy(settings)
    )

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.logic.workflows.uploads import (
    InvalidUploadArchiveError,
    _extract_archive,
    download_verified_object,
    upload_workflow_id,
)


def test_upload_workflow_id_is_deterministic() -> None:
    assert upload_workflow_id("abc") == "upload:abc"


def test_download_is_atomically_published(tmp_path: Path) -> None:
    store = MagicMock()

    def download(_key: str, target: BytesIO) -> int:
        target.write(b"abcdef")
        return 6

    store.download.side_effect = download
    destination = tmp_path / "source.zip"

    result = download_verified_object(store, "uploads/a.zip", destination, 6)

    assert result == destination
    assert result.read_bytes() == b"abcdef"
    assert not destination.with_suffix(".part").exists()


def test_invalid_archive_is_reported_as_an_application_error(tmp_path: Path) -> None:
    source = tmp_path / "not-a-zip"
    source.write_bytes(b"not a zip")

    with pytest.raises(InvalidUploadArchiveError):
        _extract_archive(source, tmp_path / "out")

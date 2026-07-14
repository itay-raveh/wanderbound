from inspect import unwrap
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.logic.workflows.uploads import (
    InvalidUploadArchiveError,
    _extract_archive,
    download_verified_object,
    upload_import_workflow,
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


async def test_upload_workflow_persists_ingestion_progress() -> None:
    processing = {
        "operation_id": "operation-id",
        "uid": 42,
        "upload_generation": 1,
        "trips_folder": "/data/trips",
        "album_ids": [],
    }
    with (
        patch(
            "app.logic.workflows.uploads.download_upload",
            new=AsyncMock(return_value="/work/source.zip"),
        ),
        patch(
            "app.logic.workflows.uploads.extract_upload",
            new=AsyncMock(return_value="/work/extracted"),
        ),
        patch(
            "app.logic.workflows.uploads.finalize_upload",
            new=AsyncMock(return_value=processing),
        ),
        patch(
            "app.logic.workflows.uploads.complete_upload",
            new=AsyncMock(return_value=42),
        ),
        patch("app.logic.workflows.uploads.evict_after_upload", new=AsyncMock()),
        patch("app.logic.workflows.uploads.DBOS.start_workflow_async", new=AsyncMock()),
        patch(
            "app.logic.workflows.uploads.DBOS.set_event_async", new=AsyncMock()
        ) as emit,
    ):
        await unwrap(upload_import_workflow)("upload-id")

    assert emit.await_args_list == [
        (("0", {"type": "phase", "phase": "downloading"}),),
        (("1", {"type": "phase", "phase": "validating"}),),
        (("2", {"type": "phase", "phase": "importing"}),),
        (("3", {"type": "complete"}),),
    ]

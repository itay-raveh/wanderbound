import asyncio
from collections.abc import Callable
from inspect import unwrap
from io import BytesIO
from pathlib import Path
from threading import Event
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import app.logic.workflows.uploads as upload_workflows
from app.logic.workflows.uploads import (
    InvalidUploadArchiveError,
    _extract_archive,
    download_verified_object,
    upload_import_workflow,
    upload_workflow_id,
)
from app.models.processing import UploadSession, UploadStatus
from app.models.upload import TripChoice


def test_upload_workflow_id_is_deterministic() -> None:
    assert upload_workflow_id("abc") == "upload:abc"


def test_download_is_atomically_published(tmp_path: Path) -> None:
    store = MagicMock()
    progress: list[tuple[int, int]] = []

    def download(_key: str, target: BytesIO, report: Callable[[int], None]) -> int:
        target.write(b"abcdef")
        report(6)
        return 6

    store.download.side_effect = download
    destination = tmp_path / "source.zip"

    result = download_verified_object(
        store, "uploads/a.zip", destination, 6, progress.append
    )

    assert result == destination
    assert result.read_bytes() == b"abcdef"
    assert not destination.with_suffix(".part").exists()
    assert progress == [(0, 6), (6, 6)]


def test_invalid_archive_is_reported_as_an_application_error(tmp_path: Path) -> None:
    source = tmp_path / "not-a-zip"
    source.write_bytes(b"not a zip")

    with pytest.raises(InvalidUploadArchiveError):
        _extract_archive(source, tmp_path / "out", ["trip"])


async def test_inspection_persists_choices_before_waiting(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    with source.open("wb") as target:
        target.write(b"placeholder")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upload.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    upload = UploadSession.new(
        owner="uid:42",
        provider_upload_id="provider-id",
        filename="polarsteps.zip",
        content_type="application/zip",
        size_bytes=1,
    )
    upload.status = "processing"
    upload_id = upload.upload_id
    async with AsyncSession(engine) as session:
        session.add(upload)
        await session.commit()

    with (
        patch.object(upload_workflows, "get_engine", return_value=engine),
        patch.object(
            upload_workflows,
            "inspect_archive",
            return_value=[TripChoice(id="trip-a", label="trip-a")],
        ),
    ):
        choices = await unwrap(upload_workflows.inspect_upload)(upload_id, str(source))

    async with AsyncSession(engine) as session:
        saved = await session.get_one(UploadSession, upload_id)
    await engine.dispose()
    assert choices == [{"id": "trip-a", "label": "trip-a"}]
    assert saved.status == "awaiting_selection"
    assert [choice.id for choice in saved.trip_choices] == ["trip-a"]


async def test_progress_runner_persists_absolute_updates() -> None:
    runner = getattr(upload_workflows, "_run_with_progress", None)
    assert runner is not None

    def operation(progress: Callable[[tuple[int, int]], None]) -> str:
        progress((0, 10))
        progress((4, 10))
        progress((10, 10))
        return "finished"

    with patch(
        "app.logic.workflows.uploads.DBOS.write_stream_async", new=AsyncMock()
    ) as write:
        result = await runner("downloading", operation)

    assert result == "finished"
    assert write.await_args_list == [
        (
            (
                "progress",
                {
                    "type": "progress",
                    "phase": "downloading",
                    "done": done,
                    "total": 10,
                },
            ),
        )
        for done in (0, 4, 10)
    ]


async def test_progress_runner_joins_worker_before_stream_error_escapes() -> None:
    started = Event()
    release = Event()
    finished = Event()

    def operation(progress: Callable[[tuple[int, int]], None]) -> None:
        progress((0, 1))
        started.set()
        release.wait(timeout=1)
        finished.set()

    with patch(
        "app.logic.workflows.uploads.DBOS.write_stream_async",
        new=AsyncMock(side_effect=RuntimeError("stream unavailable")),
    ):
        running = asyncio.create_task(
            upload_workflows._run_with_progress("downloading", operation)
        )
        assert await asyncio.to_thread(started.wait, 1)
        await asyncio.sleep(0)
        worker_was_joined = not running.done()
        release.set()
        with pytest.raises(RuntimeError, match="stream unavailable"):
            await running

    assert worker_was_joined
    assert finished.is_set()


@pytest.mark.parametrize("conflict", [False, True])
async def test_upload_workflow_persists_ingestion_progress(*, conflict: bool) -> None:
    choices = [{"id": "trip-a", "label": "trip-a"}]
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
            "app.logic.workflows.uploads.inspect_upload",
            new=AsyncMock(return_value=choices),
            create=True,
        ) as inspect,
        patch(
            "app.logic.workflows.uploads.DBOS.recv_async",
            new=AsyncMock(return_value=["trip-a"]),
        ) as receive,
        patch(
            "app.logic.workflows.uploads.extract_upload",
            new=AsyncMock(return_value="/work/extracted"),
        ) as extract,
        patch(
            "app.logic.workflows.uploads.finalize_upload",
            new=AsyncMock(return_value=None if conflict else processing),
        ),
        patch(
            "app.logic.workflows.uploads.terminate_upload", new=AsyncMock()
        ) as terminate,
        patch(
            "app.logic.workflows.uploads.complete_upload",
            new=AsyncMock(return_value=42),
        ),
        patch("app.logic.workflows.uploads.evict_after_upload", new=AsyncMock()),
        patch("app.logic.workflows.uploads.DBOS.start_workflow_async", new=AsyncMock()),
        patch(
            "app.logic.workflows.uploads.DBOS.write_stream_async", new=AsyncMock()
        ) as write,
        patch(
            "app.logic.workflows.uploads.DBOS.close_stream_async", new=AsyncMock()
        ) as close,
    ):
        await unwrap(upload_import_workflow)("upload-id")

    if conflict:
        terminate.assert_awaited_once_with("upload-id", "failed", "upload_conflict")
        assert write.await_args_list[-1] == (
            ("progress", {"type": "error", "error_code": "upload_conflict"}),
        )
        return

    inspect.assert_awaited_once_with("upload-id", "/work/source.zip")
    receive.assert_awaited_once()
    extract.assert_awaited_once_with("upload-id", "/work/source.zip", ["trip-a"])
    assert write.await_args_list == [
        (
            (
                "progress",
                {"type": "selection_required", "choices": choices},
            ),
        ),
        (
            (
                "progress",
                {"type": "progress", "phase": "importing", "done": 0, "total": 1},
            ),
        ),
        (
            (
                "progress",
                {"type": "progress", "phase": "importing", "done": 1, "total": 1},
            ),
        ),
        (("progress", {"type": "complete"}),),
    ]
    close.assert_awaited_once_with("progress")


@pytest.mark.parametrize(
    ("initial_status", "inspect_error", "terminal_status", "error_code"),
    [
        ("awaiting_selection", None, "aborted", None),
        ("processing", InvalidUploadArchiveError(), "failed", "upload_invalid_zip"),
    ],
)
async def test_upload_workflow_cleans_up_terminal_uploads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initial_status: UploadStatus,
    inspect_error: Exception | None,
    terminal_status: UploadStatus,
    error_code: str | None,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upload.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    upload = UploadSession.new(
        owner="uid:42",
        provider_upload_id="provider-id",
        filename="polarsteps.zip",
        content_type="application/zip",
        size_bytes=1,
    )
    upload.status = initial_status
    upload_id = upload.upload_id
    object_key = upload.object_key
    async with AsyncSession(engine) as session:
        session.add(upload)
        await session.commit()
    workspace = tmp_path / "upload-work" / upload_id
    workspace.mkdir(parents=True)
    (workspace / "source.zip").write_bytes(b"upload")
    store = MagicMock()
    settings = upload_workflows.get_settings()
    monkeypatch.setattr(settings, "DATA_FOLDER", tmp_path)
    monkeypatch.setattr(settings, "UPLOAD_SESSION_TTL_SECONDS", 1)
    monkeypatch.setattr(upload_workflows, "get_engine", lambda: engine)
    monkeypatch.setattr(upload_workflows, "_store", lambda: store)
    monkeypatch.setattr(
        upload_workflows,
        "terminate_upload",
        unwrap(upload_workflows.terminate_upload),
    )

    with (
        patch(
            "app.logic.workflows.uploads.download_upload",
            new=AsyncMock(return_value="/work/source.zip"),
        ),
        patch(
            "app.logic.workflows.uploads.inspect_upload",
            new=AsyncMock(return_value=[{"id": "trip-a", "label": "trip-a"}]),
        ) as inspect,
        patch(
            "app.logic.workflows.uploads.DBOS.recv_async",
            new=AsyncMock(return_value=None),
        ),
        patch("app.logic.workflows.uploads.DBOS.write_stream_async", new=AsyncMock()),
        patch("app.logic.workflows.uploads.DBOS.close_stream_async", new=AsyncMock()),
    ):
        inspect.side_effect = inspect_error
        await unwrap(upload_import_workflow)(upload_id)

    async with AsyncSession(engine) as session:
        saved = await session.get_one(UploadSession, upload_id)
    await engine.dispose()
    assert saved.status == terminal_status
    assert saved.error_code == error_code
    assert saved.completed_at is not None
    assert not workspace.exists()
    store.delete.assert_called_once_with(object_key)

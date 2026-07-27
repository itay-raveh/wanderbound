from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlmodel import col, select

from app.core.config import get_settings
from app.logic.uploads.finalize import finalize_upload_session
from app.models.processing import ProcessingOperation, UploadSession
from tests.factories import PS_USER, TRIPS, make_user

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


@asynccontextmanager
async def _lock(*, acquired: bool) -> AsyncIterator[bool]:
    yield acquired


@pytest.fixture(autouse=True)
def acquire_upload_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.logic.uploads.finalize.try_advisory_lock",
        lambda _key: _lock(acquired=True),
    )


def _local_upload(tmp_path: Path, name: str) -> tuple[UploadSession, Path]:
    source = tmp_path / name
    (source / "trip" / "trip-1").mkdir(parents=True)
    upload = UploadSession.new(
        owner="local",
        provider_upload_id="provider-id",
        filename="polarsteps.zip",
        content_type="application/zip",
        size_bytes=1,
    )
    upload.status = "processing"
    return upload, source


async def test_finalization_is_idempotent_across_database_and_filesystem(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    (tmp_path / "users").mkdir()
    source = tmp_path / "extracted"
    (source / "trip" / "trip-1").mkdir(parents=True)
    (source / "trip" / "trip-1" / "payload.txt").write_text("new")
    user = make_user(uid=222_222_221, album_ids=["old"])
    (user.trips_folder / "old").mkdir(parents=True)
    (user.trips_folder / "old" / "payload.txt").write_text("old")
    session.add(user)
    session.add(
        ProcessingOperation(
            operation_id="old-op",
            uid=user.id,
            upload_generation=4,
            workflow_id="processing:old-op",
        )
    )
    upload = UploadSession.new(
        owner=f"uid:{user.id}",
        provider_upload_id="provider-id",
        filename="polarsteps.zip",
        content_type="application/zip",
        size_bytes=1,
    )
    upload.status = "processing"
    session.add(upload)
    await session.commit()
    monkeypatch.setattr(
        "app.logic.uploads.finalize.scan_user_folder", lambda _path: (PS_USER, TRIPS)
    )

    first = await finalize_upload_session(session, upload, source)
    second = await finalize_upload_session(session, upload, source)
    assert first is not None
    assert second is not None

    operations = (
        await session.exec(
            select(ProcessingOperation).where(col(ProcessingOperation.uid) == user.id)
        )
    ).all()
    assert first[0] == second[0]
    assert len(operations) == 2
    assert first[1].upload_generation == 5
    assert user.album_ids == ["old", "trip-1"]
    assert first[0].user.album_ids == ["old", "trip-1"]
    assert (user.trips_folder / "old" / "payload.txt").read_text() == "old"
    assert (user.trips_folder / "trip-1" / "payload.txt").read_text() == "new"
    assert not list(get_settings().USERS_FOLDER.glob("*.upload-backup-*"))


async def test_local_finalization_creates_and_updates_the_polarsteps_user(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    (tmp_path / "users").mkdir()
    first_upload, first_source = _local_upload(tmp_path, "local-create")
    session.add(first_upload)
    monkeypatch.setattr(
        "app.logic.uploads.finalize.scan_user_folder",
        lambda _path: (PS_USER, TRIPS),
    )

    finalized = await finalize_upload_session(session, first_upload, first_source)
    assert finalized is not None
    _result, _operation, user = finalized

    assert user.id == PS_USER.id
    assert user.google_sub is None
    assert user.microsoft_sub is None
    user.first_name = "Edited"
    user.album_ids = ["old-trip"]
    session.add(user)
    await session.commit()

    second_upload, second_source = _local_upload(tmp_path, "local-update")
    session.add(second_upload)

    finalized = await finalize_upload_session(session, second_upload, second_source)
    assert finalized is not None
    _result, _operation, updated = finalized

    assert updated.id == user.id
    assert updated.first_name == "Edited"
    assert updated.album_ids == ["old-trip", "trip-1"]


async def test_local_finalization_rejects_a_concurrent_upload_for_the_same_user(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    (tmp_path / "users").mkdir()
    upload, source = _local_upload(tmp_path, "local-conflict")
    session.add(upload)
    monkeypatch.setattr(
        "app.logic.uploads.finalize.scan_user_folder",
        lambda _path: (PS_USER, TRIPS),
    )
    monkeypatch.setattr(
        "app.logic.uploads.finalize.try_advisory_lock",
        lambda _key: _lock(acquired=False),
        raising=False,
    )

    assert await finalize_upload_session(session, upload, source) is None

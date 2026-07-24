from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sqlmodel import col, select

from app.core.config import get_settings
from app.logic.uploads.finalize import finalize_upload_session
from app.models.processing import ProcessingOperation, UploadSession
from tests.factories import PS_USER, TRIPS, make_user

if TYPE_CHECKING:
    import pytest
    from sqlmodel.ext.asyncio.session import AsyncSession


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

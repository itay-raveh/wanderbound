"""Tests for direct-media imports."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.logic.media_import import ImportRequest, SavedInput, import_saved_media
from app.logic.panorama.inspection import inspect_panorama
from app.models.album_media import AlbumMedia
from tests.factories import AID, DEFAULT_MEDIA_NAME, create_test_jpeg, insert_album

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


async def test_import_preserves_raw_panorama_candidate(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    album = await insert_album(session, 1)
    raw = create_test_jpeg(tmp_path / "raw.jpg", 200, 100)
    album_dir = tmp_path / "album"
    album_dir.mkdir()
    monkeypatch.setattr(
        "app.logic.media_import._generated_name", lambda _suffix: DEFAULT_MEDIA_NAME
    )

    names = await import_saved_media(
        session,
        album=album,
        album_dir=album_dir,
        request=ImportRequest(context="cover"),
        saved=[SavedInput(path=raw, size=raw.stat().st_size)],
    )

    assert names == [DEFAULT_MEDIA_NAME]
    row = await session.get_one(AlbumMedia, (1, AID, DEFAULT_MEDIA_NAME))
    assert row.panorama is not None
    original_path = row.panorama.original_path
    assert original_path is not None
    assert original_path == f".panoramas/originals/{Path(DEFAULT_MEDIA_NAME).stem}.jpg"
    original = album_dir / original_path
    assert original.read_bytes() == raw.read_bytes()
    assert inspect_panorama(original) is not None


async def test_failed_import_removes_preserved_panorama_original(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    album = await insert_album(session, 1)
    raw = create_test_jpeg(tmp_path / "raw.jpg", 200, 100)
    album_dir = tmp_path / "album"
    album_dir.mkdir()
    monkeypatch.setattr(
        "app.logic.media_import._generated_name", lambda _suffix: DEFAULT_MEDIA_NAME
    )

    async def fail_commit() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await import_saved_media(
            session,
            album=album,
            album_dir=album_dir,
            request=ImportRequest(context="cover"),
            saved=[SavedInput(path=raw, size=raw.stat().st_size)],
        )

    assert not (album_dir / DEFAULT_MEDIA_NAME).exists()
    assert not (
        album_dir / ".panoramas/originals" / f"{Path(DEFAULT_MEDIA_NAME).stem}.jpg"
    ).exists()

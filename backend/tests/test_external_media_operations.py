from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.logic.external_media.album_media import replace_album_media_from_saved
from app.logic.media_import import SavedInput
from app.models.album_media import AlbumMedia, AlbumMediaUndoSnapshot

from .factories import AID, create_test_jpeg, insert_album, insert_album_media

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


VALID_NAME = (
    "11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg"
)


async def test_replace_preserves_media_name_and_creates_undo(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    uid = 1
    album = await insert_album(session, uid)
    album_dir = tmp_path
    original = create_test_jpeg(album_dir / VALID_NAME, 640, 480)
    media = await insert_album_media(
        session,
        uid,
        name=VALID_NAME,
        width=640,
        height=480,
    )
    media.byte_size = original.stat().st_size
    session.add(media)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    result = await replace_album_media_from_saved(
        session,
        album=album,
        album_dir=album_dir,
        media_name=VALID_NAME,
        saved=SavedInput(path=replacement, size=replacement.stat().st_size),
        source_ref_id=None,
    )

    assert result.name == VALID_NAME
    row = await session.get_one(AlbumMedia, (uid, AID, VALID_NAME))
    assert row.width == 1600
    assert row.height == 1200
    snap = await session.get_one(AlbumMediaUndoSnapshot, (uid, AID, VALID_NAME))
    assert snap.expires_at > snap.created_at


async def test_replace_rejects_photo_video_mismatch(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    uid = 1
    album = await insert_album(session, uid)
    media = await insert_album_media(
        session,
        uid,
        name=VALID_NAME,
        width=640,
        height=480,
    )
    media.kind = "video"
    session.add(media)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    with pytest.raises(ValueError, match="Cannot replace video with photo"):
        await replace_album_media_from_saved(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
            saved=SavedInput(path=replacement, size=replacement.stat().st_size),
            source_ref_id=None,
        )

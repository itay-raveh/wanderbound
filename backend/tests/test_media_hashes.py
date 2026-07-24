from pathlib import Path
from typing import TYPE_CHECKING

import imagehash
import numpy as np
import pytest

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

from app.logic.layout.media import Media
from app.logic.media_import import ImportRequest, persist_imported_media
from app.logic.media_upgrade.hashes import (
    compute_serialized_media_hash,
    compute_serialized_media_hashes,
    deserialize_media_hash,
    serialize_media_hash,
)
from app.models.album_media import AlbumMedia
from tests.factories import (
    AID,
    DEFAULT_MEDIA_NAME,
    create_test_jpeg,
    insert_album,
    insert_album_media,
)


def _hash(value: int) -> imagehash.ImageHash:
    bits = np.array([(value >> i) & 1 for i in range(64)], dtype=bool)
    return imagehash.ImageHash(bits)


def test_serializes_and_restores_photo_hash() -> None:
    media_hash = _hash(0x1234ABCD)

    serialized = serialize_media_hash(media_hash)

    assert serialized == [str(media_hash)]
    assert deserialize_media_hash(serialized) == media_hash


def test_serializes_and_restores_video_hashes() -> None:
    media_hash = [_hash(0x1234), _hash(0xABCD)]

    serialized = serialize_media_hash(media_hash)

    assert serialized == [str(value) for value in media_hash]
    assert deserialize_media_hash(serialized) == media_hash


@pytest.mark.parametrize("value", [[], ["0"], ["not-a-valid-hash"]])
def test_rejects_noncanonical_persisted_hashes(value: list[str]) -> None:
    with pytest.raises(ValueError, match="64-bit"):
        deserialize_media_hash(value)


def test_computes_serialized_photo_hash(tmp_path: Path) -> None:
    photo = create_test_jpeg(tmp_path / "photo.jpg", 800, 600)

    hashes = compute_serialized_media_hash(photo)

    assert len(hashes) == 1
    assert len(hashes[0]) == 16


def test_bulk_hashing_skips_unreadable_media(tmp_path: Path) -> None:
    photo = create_test_jpeg(tmp_path / "photo.jpg", 800, 600)
    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"not an image")

    hashes = compute_serialized_media_hashes([photo, corrupt])

    assert set(hashes) == {photo.name}


async def test_album_media_persists_perceptual_hashes(
    session: AsyncSession,
) -> None:
    await insert_album(session, 1)
    media = await insert_album_media(session, 1, name="photo.jpg")
    media.perceptual_hashes = ["0123456789abcdef"]
    session.add(media)
    await session.commit()
    session.expunge_all()

    restored = await session.get_one(AlbumMedia, (1, AID, "photo.jpg"))

    assert restored.perceptual_hashes == ["0123456789abcdef"]


def test_album_media_hashes_stay_out_of_api_schema() -> None:
    schema = AlbumMedia.model_json_schema()
    media = AlbumMedia(
        uid=1,
        aid=AID,
        name="photo.jpg",
        kind="photo",
        width=800,
        height=600,
        byte_size=1,
        perceptual_hashes=["0123456789abcdef"],
    )

    assert "perceptual_hashes" not in schema["properties"]
    assert "perceptual_hashes" not in media.model_dump()


async def test_manual_import_persists_hash_with_media_row(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album = await insert_album(session, 1)
    create_test_jpeg(tmp_path / DEFAULT_MEDIA_NAME, 800, 600)

    await persist_imported_media(
        session,
        album=album,
        request=ImportRequest(context="cover"),
        imported=[Media(name=DEFAULT_MEDIA_NAME, width=800, height=600)],
        album_dir=tmp_path,
    )

    restored = await session.get_one(AlbumMedia, (1, AID, DEFAULT_MEDIA_NAME))
    assert restored.perceptual_hashes is not None
    assert len(restored.perceptual_hashes) == 1

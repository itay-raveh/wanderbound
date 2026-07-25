import os
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import imagehash
import numpy as np
import pytest
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

from app.logic.layout.media import Media
from app.logic.media_import import ImportRequest, persist_imported_media
from app.logic.media_upgrade.hash_cache import local_hash_cache
from app.logic.media_upgrade.hashes import (
    compute_serialized_media_hash,
    compute_serialized_media_hashes,
    deserialize_media_hash,
    serialize_media_hash,
    try_compute_serialized_media_hash,
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


def test_rejects_obsolete_multi_frame_hashes() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        deserialize_media_hash([str(_hash(0x1234)), str(_hash(0xABCD))])


@pytest.mark.parametrize(
    ("value", "message"),
    [([], "exactly one"), (["0"], "64-bit"), (["not-a-valid-hash"], "64-bit")],
)
def test_rejects_noncanonical_persisted_hashes(value: list[str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
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


def test_bulk_hashing_ignores_videos(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"not-even-a-video")

    hashes = compute_serialized_media_hashes([video])

    assert hashes == {}


def test_single_best_effort_hashing_ignores_videos(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"not-even-a-video")

    assert try_compute_serialized_media_hash(video) is None


def test_cached_hash_uses_complete_file_identity(tmp_path: Path) -> None:
    photo = create_test_jpeg(tmp_path / "photo.jpg", 800, 600)
    stat = photo.stat()
    cached_hash = MagicMock(return_value=_hash(0x1234))

    hashes = compute_serialized_media_hashes(
        [photo], workers=1, cached_hash=cached_hash
    )

    assert hashes == {photo.name: [str(_hash(0x1234))]}
    cached_hash.assert_called_once_with(
        photo,
        stat.st_dev,
        stat.st_ino,
        stat.st_size,
        stat.st_mtime_ns,
    )


def test_local_hash_cache_recomputes_same_size_mtime_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    album_dir = tmp_path / "1" / "trip" / "trip-1"
    album_dir.mkdir(parents=True)
    photo = album_dir / "photo.bmp"

    first = Image.new("RGB", (64, 64), "white")
    ImageDraw.Draw(first).rectangle((0, 0, 31, 63), fill="black")
    first.save(photo)
    first_stat = photo.stat()

    def settings() -> object:
        return type("Settings", (), {"USERS_FOLDER": tmp_path})()

    monkeypatch.setattr("app.logic.media_upgrade.hash_cache.get_settings", settings)
    cached_hash = local_hash_cache(album_dir)
    first_hash = cached_hash(
        photo,
        first_stat.st_dev,
        first_stat.st_ino,
        first_stat.st_size,
        first_stat.st_mtime_ns,
    )

    replacement = album_dir / "replacement.bmp"
    second = Image.new("RGB", (64, 64), "white")
    ImageDraw.Draw(second).rectangle((0, 0, 63, 31), fill="black")
    second.save(replacement)
    assert replacement.stat().st_size == first_stat.st_size
    os.utime(replacement, ns=(first_stat.st_atime_ns, first_stat.st_mtime_ns))
    replacement.replace(photo)
    second_stat = photo.stat()
    assert second_stat.st_ino != first_stat.st_ino
    assert second_stat.st_mtime_ns == first_stat.st_mtime_ns

    second_hash = cached_hash(
        photo,
        second_stat.st_dev,
        second_stat.st_ino,
        second_stat.st_size,
        second_stat.st_mtime_ns,
    )

    assert second_hash != first_hash


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

from datetime import UTC, datetime
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image

from app.logic.media_upgrade.phash_matching import HashedMedia
from app.models.google_photos import GoogleMediaFile, GoogleMediaType, PickedMediaItem


def make_hash(value: int) -> imagehash.ImageHash:
    bits = np.array([(value >> i) & 1 for i in range(64)], dtype=bool)
    return imagehash.ImageHash(bits)


def hashed_media(key: str, media_hash: imagehash.ImageHash) -> HashedMedia:
    return HashedMedia(key=key, hash=media_hash)


def make_item(
    item_id: str,
    create_time: str,
    *,
    item_type: GoogleMediaType = "PHOTO",
    video_processing_status: str | None = None,
    base_url: str = "https://lh3.googleusercontent.com/test",
    width: int | None = None,
    height: int | None = None,
) -> PickedMediaItem:
    return PickedMediaItem(
        id=item_id,
        create_time=create_time,
        type=item_type,
        media_file=GoogleMediaFile(
            base_url=base_url,
            mime_type="video/mp4" if item_type == "VIDEO" else "image/jpeg",
            filename=f"{item_id}.mp4" if item_type == "VIDEO" else f"{item_id}.jpg",
            width=width,
            height=height,
        ),
        video_processing_status=video_processing_status,
    )


def write_jpeg(
    path: Path, width: int, height: int, *, exif: bytes | None = None
) -> None:
    image = Image.new("RGB", (width, height), color=(100, 150, 200))
    kwargs: dict = {"format": "JPEG", "quality": 95}
    if exif is not None:
        kwargs["exif"] = exif
    image.save(path, **kwargs)


def write_png(path: Path, width: int, height: int) -> None:
    image = Image.new("RGBA", (width, height), color=(100, 150, 200, 255))
    image.save(path, format="PNG")


async def test_token() -> str:
    return "test-token"


def match_datetime(hour: int, minute: int = 0) -> datetime:
    return datetime(2024, 1, 15, hour, minute, tzinfo=UTC)

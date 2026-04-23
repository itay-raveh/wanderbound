import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Annotated, Self

import av
from PIL import Image, ImageOps
from PIL.Image import Resampling
from pydantic import BaseModel, StringConstraints

from app.core.resources import detect_memory_mb

# PQ (HDR10) and HLG values of AVColorTransferCharacteristic.
# https://ffmpeg.org/doxygen/trunk/pixfmt_8h.html
HDR_COLOR_TRC = frozenset({16, 18})

logger = logging.getLogger(__name__)

MEDIA_EXTENSIONS = frozenset({".jpg", ".mp4"})
# Must match frontend utils/media.ts THUMB_WIDTHS - frontend builds srcset from these.
THUMB_WIDTHS = (200, 800)
THUMB_QUALITY = 80

# Limit concurrent heavy media work (ffmpeg frame extraction, Pillow thumbnails).
_MEDIA_BASELINE_MB = 400  # Python process + other services sharing the container
_PER_MEDIA_OP_MB = 80  # Pillow load + resize + save
_media_budget = max(256, detect_memory_mb() - _MEDIA_BASELINE_MB)
media_sem = asyncio.Semaphore(max(4, min(40, _media_budget // _PER_MEDIA_OP_MB)))


@contextmanager
def open_oriented(source: Path | BytesIO) -> Iterator[Image.Image]:
    """Open an image and yield it with EXIF orientation applied."""
    with Image.open(source) as raw:
        yield ImageOps.exif_transpose(raw) or raw


def _generate_thumbnail_sync(source: Path, width: int) -> Path | None:
    with open_oriented(source) as img:
        orig_w, orig_h = img.size
        if width >= orig_w:
            return None
        out_dir = source.parent / ".thumbs" / str(width)
        out_dir.mkdir(parents=True, exist_ok=True)
        ratio = width / orig_w
        thumb = img.resize((width, round(orig_h * ratio)), Resampling.LANCZOS)
        out = out_dir / f"{source.stem}.webp"
        thumb.save(out, "WEBP", quality=THUMB_QUALITY)
        return out


async def generate_thumbnail(source: Path, width: int) -> Path | None:
    async with media_sem:
        return await asyncio.to_thread(_generate_thumbnail_sync, source, width)


def delete_thumbnails(path: Path) -> None:
    thumbs_base = path.parent / ".thumbs"
    for w in THUMB_WIDTHS:
        thumb = thumbs_base / str(w) / f"{path.stem}.webp"
        thumb.unlink(missing_ok=True)


# {uuid4}_{uuid4}.(jpg|mp4)
_UUID4 = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

MediaName = Annotated[
    str, StringConstraints(pattern=rf"^{_UUID4}_{_UUID4}\.(jpg|mp4)$")
]


def normalize_name(raw: str) -> str:
    """Fix the .jpg.jpg double-extension from the Polarsteps ZIP format."""
    return raw.replace(".jpg.jpg", ".jpg")


def is_video(name: str) -> bool:
    return name.endswith(".mp4")


def _probe_video_dimensions_sync(path: Path) -> tuple[int, int]:
    # stream.width/height are pre-rotation; rotation lives on decoded frames.
    # https://github.com/PyAV-Org/PyAV/pull/1675
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        w, h = stream.width, stream.height
        rotation = 0
        for frame in container.decode(stream):
            rotation = abs(int(frame.rotation))
            break
    if rotation in (90, 270):
        w, h = h, w
    logger.debug("av probe %s: %dx%d (rotation=%d)", path.name, w, h, rotation)
    return w, h


async def _video_dimensions(path: Path) -> tuple[int, int]:
    return await asyncio.to_thread(_probe_video_dimensions_sync, path)


class Media(BaseModel):
    name: str
    width: int
    height: int

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height

    @property
    def is_portrait(self) -> bool:
        return self.aspect_ratio < 9 / 10

    @property
    def orientation(self) -> str:
        return "p" if self.is_portrait else "l"

    @classmethod
    def load(cls, path: Path) -> Self:
        with open_oriented(path) as img:
            width, height = img.size
        return cls(
            name=normalize_name(path.name),
            width=width,
            height=height,
        )

    @classmethod
    async def probe(cls, path: Path) -> Self:
        w, h = await _video_dimensions(path)
        return cls(
            name=normalize_name(path.name),
            width=w,
            height=h,
        )


def _video_duration_sync(path: Path) -> float:
    # https://pyav.basswood-io.com/docs/stable/api/time.html
    with av.open(str(path)) as container:
        if container.duration is None:
            return 2.0  # safe fallback for sources without duration metadata
        return container.duration / av.time_base


_ROTATION_TRANSPOSE = {
    90: Image.Transpose.ROTATE_90,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_270,
}


def _frame_to_oriented_image(frame: av.VideoFrame) -> Image.Image:
    # to_image() ignores displaymatrix, so portrait phone videos save sideways.
    # https://github.com/PyAV-Org/PyAV/discussions/1676
    img = frame.to_image()
    t = _ROTATION_TRANSPOSE.get(int(frame.rotation) % 360)
    return img.transpose(t) if t else img


def _extract_frame_sync(video: Path, timestamp: float) -> Path:
    # Seek backward to keyframe, decode forward to reach exact timestamp.
    # https://pyav.basswood-io.com/docs/stable/api/container.html#av.container.InputContainer.seek
    frame_path = video.with_suffix(".jpg")
    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        container.seek(int(timestamp * av.time_base))
        for frame in container.decode(stream):
            if frame.time is not None and frame.time >= timestamp:
                _frame_to_oriented_image(frame).save(frame_path, "JPEG", quality=85)
                return frame_path
    # ts beyond duration: fall back to last frame.
    with av.open(str(video)) as container:
        last = None
        for frame in container.decode(container.streams.video[0]):
            last = frame
        if last is None:
            raise RuntimeError(f"No frames in {video}")
        _frame_to_oriented_image(last).save(frame_path, "JPEG", quality=85)
        return frame_path


async def extract_frame(video: Path, timestamp: float | None = None) -> Path:
    if timestamp is None:
        duration = await asyncio.to_thread(_video_duration_sync, video)
        timestamp = duration / 2
    async with media_sem:
        return await asyncio.to_thread(_extract_frame_sync, video, timestamp)

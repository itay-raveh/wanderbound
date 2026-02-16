import asyncio
from pathlib import Path

import cv2
from PIL import Image, ImageOps

from psagen.core.logger import get_logger
from psagen.models.layout import Photo, Video

logger = get_logger(__name__)


async def load_photo(root: Path, path: Path) -> Photo:
    return await asyncio.to_thread(_load_photo, root, path)


def _load_photo(root: Path, path: Path) -> Photo:
    with Image.open(path) as img:
        width, height = ImageOps.exif_transpose(img).size

    return Photo(
        path=path.relative_to(root),
        width=width,
        height=height,
    )


_DEFAULT_FRAME_TS = 1


async def load_video(root: Path, path: Path) -> Video:
    frame_path = await extract_frame(root, path, _DEFAULT_FRAME_TS)
    frame = await load_photo(root, frame_path)

    return Video(
        path=frame.path,
        width=frame.width,
        height=frame.height,
        src=path.relative_to(root),
        timestamp=_DEFAULT_FRAME_TS,
    )


async def extract_frame(root: Path, video_path: Path, timestamp: float) -> Path:
    return await asyncio.to_thread(_extract_frame, root, video_path, timestamp)


def _extract_frame(root: Path, video_path: Path, timestamp: float) -> Path:
    ts_str = f"{timestamp:.3f}".replace(".", "_")
    frame = root / "zz_frames" / f"{video_path.stem}__{ts_str}.png"

    if frame.exists():
        return frame

    frame.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)

    success, img = cap.read()
    cap.release()

    if not success:
        raise RuntimeError(f"Failed to extract frame at {timestamp}s from {video_path}")

    cv2.imwrite(str(frame), img)

    return frame

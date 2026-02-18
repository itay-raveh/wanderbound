import pathlib
from io import BytesIO

import anyio
import cv2
from PIL import Image, ImageOps

from psagen.core.logger import get_logger
from psagen.models.layout import Photo, Video

logger = get_logger(__name__)


async def load_photo(root: anyio.Path, path: anyio.Path) -> Photo:
    with Image.open(BytesIO(await path.read_bytes())) as img:
        width, height = ImageOps.exif_transpose(img).size

    return Photo(
        path=pathlib.Path(path.relative_to(root)),
        width=width,
        height=height,
    )


_DEFAULT_FRAME_TS = 1


async def load_video(root: anyio.Path, path: anyio.Path) -> Video:
    frame_path = await extract_frame(root, path, _DEFAULT_FRAME_TS)
    frame = await load_photo(root, frame_path)

    return Video(
        path=frame.path,
        width=frame.width,
        height=frame.height,
        src=pathlib.Path(path.relative_to(root)),
        timestamp=_DEFAULT_FRAME_TS,
    )


async def extract_frame(root: anyio.Path, video_path: anyio.Path, timestamp: float) -> anyio.Path:
    ts_str = f"{timestamp:.3f}".replace(".", "_")
    frame = root / "zz_frames" / f"{video_path.stem}__{ts_str}.png"

    if await frame.exists():
        return frame

    await frame.parent.mkdir(parents=True, exist_ok=True)

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

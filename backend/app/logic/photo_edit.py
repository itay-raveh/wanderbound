import hashlib
import json
import math
from pathlib import Path

from PIL import Image

from app.core.worker_threads import run_sync
from app.logic.layout.media import (
    THUMB_WIDTHS,
    generation_lock,
    media_limiter,
    open_oriented,
)
from app.models.album_media import PhotoEdit


def rotated_size(width: int, height: int, angle: float) -> tuple[float, float]:
    radians = math.radians(angle)
    cosine, sine = abs(math.cos(radians)), abs(math.sin(radians))
    return width * cosine + height * sine, width * sine + height * cosine


def validate_photo_edit(edit: PhotoEdit, width: int, height: int) -> None:
    rotated_width, rotated_height = rotated_size(width, height, edit.angle)
    radians = math.radians(edit.angle)
    cosine, sine = math.cos(radians), math.sin(radians)
    for x in (edit.x, edit.x + edit.width):
        for y in (edit.y, edit.y + edit.height):
            dx = (x - 0.5) * rotated_width
            dy = (y - 0.5) * rotated_height
            source_x = dx * cosine + dy * sine
            source_y = -dx * sine + dy * cosine
            if abs(source_x) > width / 2 + 0.001 or abs(source_y) > height / 2 + 0.001:
                raise ValueError("Crop contains empty space outside the rotated photo")


def fit_photo_edit(edit: PhotoEdit, width: int, height: int) -> PhotoEdit:
    try:
        validate_photo_edit(edit, width, height)
    except ValueError:
        pass
    else:
        return edit

    rotated_width, rotated_height = rotated_size(width, height, edit.angle)
    aspect = edit.width * rotated_width / (edit.height * rotated_height)
    radians = math.radians(edit.angle)
    cosine, sine = abs(math.cos(radians)), abs(math.sin(radians))
    half_height = min(
        width / (2 * (aspect * cosine + sine)),
        height / (2 * (aspect * sine + cosine)),
    )
    max_width = 2 * half_height * aspect / rotated_width
    max_height = 2 * half_height / rotated_height
    scale = min(1, max_width / edit.width, max_height / edit.height) * 0.996
    crop_width = edit.width * scale
    crop_height = edit.height * scale
    centered = PhotoEdit(
        angle=edit.angle,
        x=(1 - crop_width) / 2,
        y=(1 - crop_height) / 2,
        width=crop_width,
        height=crop_height,
    )
    dx = edit.x + edit.width / 2 - 0.5
    dy = edit.y + edit.height / 2 - 0.5
    low, high = 0.0, 1.0
    for _ in range(24):
        middle = (low + high) / 2
        candidate = centered.model_copy(
            update={"x": centered.x + dx * middle, "y": centered.y + dy * middle}
        )
        try:
            validate_photo_edit(candidate, width, height)
        except ValueError:
            high = middle
        else:
            low = middle
    return centered.model_copy(
        update={"x": centered.x + dx * low, "y": centered.y + dy * low}
    )


def edited_photo_path(
    album_dir: Path, source: Path, edit: PhotoEdit, media_name: str
) -> Path:
    stat = source.stat()
    signature = json.dumps(
        (stat.st_mtime_ns, stat.st_size, edit.model_dump()),
        sort_keys=True,
    ).encode()
    digest = hashlib.sha256(signature).hexdigest()[:20]
    return album_dir / ".edits" / Path(media_name).stem / f"{digest}.jpg"


def _remove_other_edits(keep: Path) -> None:
    for path in keep.parent.glob("*.jpg"):
        if path != keep:
            path.unlink(missing_ok=True)
            for width in THUMB_WIDTHS:
                (keep.parent / ".thumbs" / str(width) / f"{path.stem}.webp").unlink(
                    missing_ok=True
                )


def _render_photo_edit_sync(source: Path, output: Path, edit: PhotoEdit) -> None:
    with open_oriented(source) as image:
        validate_photo_edit(edit, *image.size)
        rotated = image.rotate(-edit.angle, Image.Resampling.BICUBIC, expand=True)
        left = round(edit.x * rotated.width)
        top = round(edit.y * rotated.height)
        right = round((edit.x + edit.width) * rotated.width)
        bottom = round((edit.y + edit.height) * rotated.height)
        cropped = rotated.crop((left, top, right, bottom)).convert("RGB")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".tmp")
        try:
            cropped.save(temporary, "JPEG", quality=95, subsampling=0)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)


async def render_photo_edit(
    album_dir: Path, source: Path, edit: PhotoEdit, media_name: str
) -> Path:
    output = edited_photo_path(album_dir, source, edit, media_name)
    async with generation_lock(output.parent):
        if not await run_sync(output.is_file):
            await run_sync(
                _render_photo_edit_sync,
                source,
                output,
                edit,
                limiter=media_limiter,
            )
        await run_sync(_remove_other_edits, output)
    return output

import asyncio
import logging
import math
from itertools import batched
from math import ceil
from typing import TYPE_CHECKING, NamedTuple

from .media import Media, MediaName, Photo, Video

# Global limit on concurrent ffprobe processes across all users.
_ffprobe_sem = asyncio.Semaphore(8)

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Iterable, Sequence
    from pathlib import Path

    from app.models.ids import AlbumId
    from app.models.polarsteps import PSStep
    from app.models.user import User


class Layout(NamedTuple):
    cover: MediaName
    pages: list[list[MediaName]]
    orientations: dict[MediaName, str]


logger = logging.getLogger(__name__)

# Layout heuristic for deciding whether a step description is "long"
# (takes the full main page, so cover stays in the photo pages).
# Chars-per-line and threshold are tuned to the A4-landscape step layout.
_CHARS_PER_LINE = 80
_LONG_DESCRIPTION_THRESHOLD = 1000


def _visual_length(text: str) -> int:
    """Estimate character consumption by simulating line wrapping."""
    if not text:
        return 0
    lines = 0
    for para in text.split("\n"):
        lines += math.ceil(len(para) / _CHARS_PER_LINE) if para else 1
    return lines * _CHARS_PER_LINE


def _is_long_description(description: str) -> bool:
    return _visual_length(description) > _LONG_DESCRIPTION_THRESHOLD


def _portrait_page_count(n: int) -> int:
    """Min pages for n portraits (page sizes 3, 2, 1)."""
    return ceil(n / 3)


def _landscape_page_count(n: int) -> int:
    """Min pages for n landscapes (page sizes 4, 3, 1)."""
    return 2 if n == 2 else ceil(n / 4)


def _optimal_mixed_count(p: int, l: int) -> int:
    """Find the number of 1P+2L pages that minimizes total page count."""
    best_total = p + l
    best_b = 0

    for b in range(min(p, l // 2) + 1):
        total = b + _portrait_page_count(p - b) + _landscape_page_count(l - 2 * b)

        if total < best_total:
            best_total = total
            best_b = b

    return best_b


def _three_page_count(n: int) -> int:
    """Number of 3-pages to optimally decompose n landscapes into pages of 4 and 3."""
    return -n % 4


def _pages_of(items: Iterable[str], size: int) -> Iterable[list[str]]:
    """Yield pages of the given size from items."""
    yield from (list(batch) for batch in batched(items, size, strict=False))


def _landscape_pages(items: Sequence[str]) -> Iterable[list[str]]:
    """Yield optimally packed landscape pages (sizes 4, 3, 1)."""
    n = len(items)

    if n < 3:
        yield from ([p] for p in items)
    elif n == 5:
        # Only case where 4s and 3s can't cover: 4 + 1
        yield list(items[:4])
        yield [items[4]]
    else:
        threes = _three_page_count(n)
        cut = n - 3 * threes
        yield from _pages_of(items[:cut], 4)
        yield from _pages_of(items[cut:], 3)


def _build_pages(
    portraits: Sequence[str], landscapes: Sequence[str]
) -> Iterable[list[str]]:
    mixed = _optimal_mixed_count(len(portraits), len(landscapes))

    for i in range(mixed):
        yield [portraits[i], landscapes[2 * i], landscapes[2 * i + 1]]

    yield from _pages_of(portraits[mixed:], 3)
    yield from _landscape_pages(landscapes[2 * mixed :])


def _load_photos(folder: Path) -> list[Photo]:
    """Load photo metadata from a folder (sync — runs in thread pool)."""
    return [
        Photo.load(p)
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() == ".jpg"
    ]


async def _step_media(step_dir: Path) -> AsyncIterable[Media]:
    photo_folder = step_dir / "photos"
    if photo_folder.exists():
        for photo in await asyncio.to_thread(_load_photos, photo_folder):
            yield photo

    video_folder = step_dir / "videos"
    if video_folder.exists():

        async def _probe(p: Path) -> Video:
            async with _ffprobe_sem:
                return await Video.probe(p)

        for coro in asyncio.as_completed(
            [_probe(p) for p in video_folder.iterdir() if p.suffix.lower() == ".mp4"]
        ):
            yield await coro


async def build_step_layout(user: User, aid: AlbumId, step: PSStep) -> Layout | None:
    step_dir = user.trips_folder / aid / step.folder_name

    media: list[Media] = [m async for m in _step_media(step_dir)]

    # Split and sort portraits (closest to 4/5 first)
    portraits = [
        p.name
        for p in sorted(
            (p for p in media if p.is_portrait),
            key=lambda p: p.aspect_ratio,
            reverse=True,
        )
    ]
    landscapes = [m.name for m in media if not m.is_portrait]

    if not portraits and not landscapes:
        logger.debug("Step '%s' has no media files, skipping layout", step.name)
        return None

    orientations: dict[str, str] = {m.name: m.orientation for m in media}
    cover = portraits[0] if portraits else landscapes[0]

    # If it appears on the step page, remove it from the photo pages
    if not _is_long_description(step.description):
        if cover in portraits:
            portraits.remove(cover)
        else:
            landscapes.remove(cover)

    return Layout(cover, list(_build_pages(portraits, landscapes)), orientations)

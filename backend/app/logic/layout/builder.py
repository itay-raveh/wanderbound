import asyncio
import logging
from collections.abc import AsyncIterable, Iterable, Sequence
from itertools import batched
from math import ceil
from pathlib import Path
from typing import NamedTuple

from app.models.polarsteps import PSStep
from app.models.user import User

from .media import Media, MediaName

# Global limit on concurrent ffprobe processes across all users.
_ffprobe_sem = asyncio.Semaphore(8)


class Layout(NamedTuple):
    cover: MediaName
    pages: list[list[MediaName]]
    orientations: dict[MediaName, str]


logger = logging.getLogger(__name__)


def _portrait_page_count(n: int) -> int:
    """Min pages for n portraits (page sizes 3, 2, 1)."""
    return ceil(n / 3)


def _landscape_page_count(n: int) -> int:
    """Min pages for n landscapes (page sizes 4, 3, 1)."""
    return 2 if n == 2 else ceil(n / 4)


def _three_page_count(n: int) -> int:
    """Remainder when packing n items into groups of 4, filled by groups of 3."""
    return -n % 4


def _bad_page_count(p: int, l: int) -> int:
    """Count undesirable pages: lonely portraits (1p-0l) and 3-landscape pages (0p-3l).

    Single landscapes (1l) aren't penalised — they're unavoidable edge cases
    and look fine as full-width images, unlike lonely portraits or 3-landscape
    grids which waste space or crop poorly.
    """
    lonely_p = 1 if p > 0 and p % 3 == 1 else 0
    three_l = _three_page_count(l) if l >= 3 and l != 5 else 0
    return lonely_p + three_l


def _optimal_mixed_count(p: int, l: int) -> int:
    """Find the number of 1P+2L pages that minimizes total page count.

    On ties, prefer fewer lonely-portrait and 3-landscape pages.
    """
    best_total = p + l
    best_bad = p + l
    best_b = 0

    for b in range(min(p, l // 2) + 1):
        rp, rl = p - b, l - 2 * b
        total = b + _portrait_page_count(rp) + _landscape_page_count(rl)

        if total < best_total or (
            total == best_total and _bad_page_count(rp, rl) < best_bad
        ):
            best_total = total
            best_bad = _bad_page_count(rp, rl)
            best_b = b

    return best_b


def _pages_of(items: Iterable[str], size: int) -> Iterable[list[str]]:
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


def _load_photos(folder: Path) -> list[Media]:
    """Load photo metadata from a folder (sync - runs in thread pool)."""
    return [
        Media.load(p)
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

        async def _probe(p: Path) -> Media:
            async with _ffprobe_sem:
                return await Media.probe(p)

        for coro in asyncio.as_completed(
            [_probe(p) for p in video_folder.iterdir() if p.suffix.lower() == ".mp4"]
        ):
            yield await coro


async def build_step_layout(user: User, aid: str, step: PSStep) -> Layout | None:
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

    return Layout(cover, list(_build_pages(portraits, landscapes)), orientations)

"""Reconciliation pipeline for re-uploaded user data.

Matches existing album edits (page layouts, covers, step modifications)
with potentially changed media on disk after a re-upload.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from app.logic.layout import Layout
from app.logic.layout.media import Media, normalize_name
from app.logic.processing import (
    DbRow,
    PhaseUpdate,
    TripResults,
    _media_sem,
    build_step,
    cover_name_from_trip,
    drain_queue,
    fetch_layouts,
    load_trip_data,
    prepare_media,
    run_elevations,
    run_weather,
    track_iter,
)
from app.models.album import Album
from app.models.polarsteps import PSStep
from app.models.step import Step
from app.models.user import User

logger = logging.getLogger(__name__)


def _scan_step_media(trip_dir: Path, ps_step: PSStep) -> set[str]:
    """Scan a step's photo/video folders and return normalized filenames."""
    step_folder = trip_dir / ps_step.folder_name
    found: set[str] = set()
    for sub in ("photos", "videos"):
        folder = step_folder / sub
        if not folder.exists():
            continue
        for f in folder.iterdir():
            if f.is_file():
                found.add(normalize_name(f.name))
    return found


def _pick_cover(
    pages: list[list[str]],
    unused: list[str],
    media_dict: dict[str, str],
) -> str | None:
    """Pick a cover photo, preferring portraits."""
    candidates = [f for pg in pages for f in pg] + unused
    portraits = [f for f in candidates if media_dict.get(f) == "p"]
    return portraits[0] if portraits else (candidates[0] if candidates else None)


def _reconcile_step(
    step: Step,
    ps_step: PSStep,
    disk_media: set[str],
    all_on_disk: set[str],
    media_dict: dict[str, str],
) -> Step:
    """Update a single step's media references and metadata."""
    old_media: set[str] = set()
    for pg in step.pages:
        old_media.update(pg)
    if step.cover:
        old_media.add(step.cover)
    old_media.update(step.unused)

    missing = old_media - all_on_disk
    # intersect with all_on_disk: flatten may overwrite dupes
    added = (disk_media - old_media) & all_on_disk

    step.pages = [
        p for p in ([f for f in pg if f not in missing] for pg in step.pages) if p
    ]
    step.unused = [f for f in step.unused if f not in missing] + sorted(added)

    if step.cover and step.cover in missing:
        step.cover = _pick_cover(step.pages, step.unused, media_dict)

    step.name = ps_step.name
    step.description = ps_step.description
    step.timestamp = ps_step.timestamp
    step.timezone_id = ps_step.timezone_id
    step.location = ps_step.location
    return step


async def _probe_orientations(
    trip_dir: Path,
    steps: list[Step],
    known: dict[str, str],
) -> dict[str, str]:
    """Probe orientations for unknown media files, return full merged dict."""
    to_probe: set[str] = set()
    for step_obj in steps:
        for pg in step_obj.pages:
            to_probe.update(f for f in pg if f not in known)
        if step_obj.cover and step_obj.cover not in known:
            to_probe.add(step_obj.cover)
        to_probe.update(f for f in step_obj.unused if f not in known)

    async def _probe(name: str) -> tuple[str, str]:
        async with _media_sem:
            try:
                m = await asyncio.to_thread(Media.load, trip_dir / name)
            except OSError, ValueError:
                return name, "l"
            else:
                return name, m.orientation

    probed = await asyncio.gather(*[_probe(f) for f in to_probe])
    return {**known, **dict(probed)}


def _fix_album_covers(
    album: Album,
    all_on_disk: set[str],
    cover_name: str,
    steps: list[Step],
) -> None:
    """Ensure album cover photos reference files that exist on disk."""
    first_step_cover = next((s.cover for s in steps if s.cover), None)
    cover_fallback = (
        cover_name
        if cover_name in all_on_disk
        else (first_step_cover or next(iter(all_on_disk), ""))
    )
    for attr in ("front_cover_photo", "back_cover_photo"):
        if getattr(album, attr) not in all_on_disk:
            setattr(album, attr, cover_fallback)


async def _process_new_steps(  # noqa: PLR0913
    user: User,
    aid: str,
    new_ps_steps: list[PSStep],
    cover_name: str,
    cover_orientation: str,
    step_out: list[Step],
) -> AsyncIterator[PhaseUpdate]:
    """Run full processing (elevations, weather, layouts) for new steps."""
    logger.info("Processing %d new steps for album %s", len(new_ps_steps), aid)
    queue: asyncio.Queue[PhaseUpdate | None] = asyncio.Queue()
    n_new = len(new_ps_steps)
    new_locs = [s.location for s in new_ps_steps]

    async def _fetch() -> dict[int, Layout | None]:
        return dict(
            await track_iter(
                "layouts",
                n_new,
                fetch_layouts(user, aid, new_ps_steps),
                queue,
            )
        )

    async def _phases() -> TripResults:
        try:
            async with asyncio.TaskGroup() as tg:
                elev_task = tg.create_task(run_elevations(new_locs, n_new, queue))
                weather_task = tg.create_task(run_weather(new_ps_steps, n_new, queue))
                layout_task = tg.create_task(_fetch())
        finally:
            await queue.put(None)
        return TripResults(
            elevations=elev_task.result(),
            weather_by_idx=weather_task.result(),
            layout_by_idx=layout_task.result(),
            cover_name=cover_name,
            cover_orientation=cover_orientation,
        )

    runner = asyncio.create_task(_phases())
    async for event in drain_queue(runner, queue):
        yield event

    results = await runner
    weathers = [results.weather_by_idx[i] for i in range(n_new)]
    layouts_list = [results.layout_by_idx[i] for i in range(n_new)]
    step_out.extend(
        build_step(user.id, aid, ps, elev, wthr, layout)
        for ps, elev, wthr, layout in zip(
            new_ps_steps, results.elevations, weathers, layouts_list, strict=True
        )
    )


async def reconcile_trip(
    user: User,
    trip_dir: Path,
    album: Album,
    existing_steps: list[Step],
    db_out: list[DbRow],
) -> AsyncIterator[PhaseUpdate]:
    """Reconcile an existing album with re-uploaded data.

    Preserves user edits (page layouts, covers) while adapting to
    changed media. New steps get full processing; existing steps
    get media reconciliation.
    """
    aid = trip_dir.name
    trip, _locations = await asyncio.to_thread(load_trip_data, trip_dir)
    logger.info(
        "Reconciling '%s' with %d steps (%d existing)",
        trip.title,
        trip.step_count,
        len(existing_steps),
    )

    # Phase 1: Build step→media map BEFORE flattening (concurrent scans)
    scan_results = await asyncio.gather(
        *[asyncio.to_thread(_scan_step_media, trip_dir, ps) for ps in trip.all_steps]
    )
    step_media_map = {
        ps.id: media for ps, media in zip(trip.all_steps, scan_results, strict=True)
    }

    # Phase 2: Prepare media (flatten + cover + frames + thumbs)
    queue: asyncio.Queue[PhaseUpdate | None] = asyncio.Queue()
    cover_name = cover_name_from_trip(trip)

    async def _phases() -> str:
        try:
            return await prepare_media(
                trip_dir, cover_name, trip.cover_photo_path, queue
            )
        finally:
            await queue.put(None)

    runner = asyncio.create_task(_phases())
    async for event in drain_queue(runner, queue):
        yield event
    cover_orientation = await runner

    # Phase 3: New steps get full processing
    db_by_step_id = {s.id: s for s in existing_steps}
    new_ps_steps = [ps for ps in trip.all_steps if ps.id not in db_by_step_id]

    new_step_objects: list[Step] = []
    if new_ps_steps:
        async for event in _process_new_steps(
            user, aid, new_ps_steps, cover_name, cover_orientation, new_step_objects
        ):
            yield event

    # Phase 4: Reconcile existing steps
    all_on_disk = {
        normalize_name(f.name)
        for f in trip_dir.iterdir()  # noqa: ASYNC240
        if f.is_file()
    }
    reconciled_steps = [
        _reconcile_step(
            db_by_step_id[ps.id],
            ps,
            step_media_map.get(ps.id, set()),
            all_on_disk,
            album.media,
        )
        for ps in trip.all_steps
        if ps.id in db_by_step_id
    ]

    # Phase 5: Reconcile album media orientations
    merged_media: dict[str, str] = {cover_name: cover_orientation}
    merged_media |= {n: o for n, o in album.media.items() if n in all_on_disk}
    album.media = await _probe_orientations(
        trip_dir, [*new_step_objects, *reconciled_steps], merged_media
    )

    _fix_album_covers(album, all_on_disk, cover_name, reconciled_steps)
    album.title = trip.title
    album.subtitle = trip.subtitle

    db_out.append(album)
    db_out.extend(reconciled_steps)
    db_out.extend(new_step_objects)

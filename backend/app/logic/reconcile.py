"""Reconciliation pipeline for re-uploaded user data.

Matches existing album edits (page layouts, covers, step modifications)
with potentially changed media on disk after a re-upload.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import structlog

from app.core.http_clients import HttpClients
from app.core.worker_threads import run_sync
from app.logic.layout import Layout
from app.logic.layout.media import Media, media_limiter, normalize_name
from app.logic.media_upgrade.hashes import compute_serialized_media_hashes
from app.logic.trip_processing import (
    DbRow,
    PhaseUpdate,
    ProcessingEvent,
    TripResults,
    build_album_media_rows,
    build_segment_objects,
    build_step,
    count_segments,
    cover_name_from_trip,
    drain_queue,
    fetch_layouts,
    load_trip_data,
    multi_day_hike_ranges,
    prepare_media,
    run_elevations,
    run_weather,
    track_iter,
)
from app.models.album import Album
from app.models.album_media import AlbumMedia, StepPageMedia, StepUnusedMedia
from app.models.polarsteps import PSStep
from app.models.step import Step, StepRead
from app.models.user import User

logger = structlog.get_logger(__name__)


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
    media_by_name: dict[str, Media],
) -> str | None:
    """Pick a cover photo, preferring portraits."""
    candidates = [f for pg in pages for f in pg] + unused
    portraits = [f for f in candidates if (m := media_by_name.get(f)) and m.is_portrait]
    return portraits[0] if portraits else (candidates[0] if candidates else None)


def _reconcile_step(
    step: StepRead,
    ps_step: PSStep,
    disk_media: set[str],
    all_on_disk: set[str],
    media_by_name: dict[str, Media],
) -> StepRead:
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
        step.cover = _pick_cover(step.pages, step.unused, media_by_name)

    step.name = ps_step.name
    step.description = ps_step.description
    step.timestamp = ps_step.timestamp
    step.timezone_id = ps_step.timezone_id
    step.location = ps_step.location
    return step


async def _probe_media(
    trip_dir: Path,
    steps: list[StepRead],
    known: dict[str, Media],
) -> list[Media]:
    """Probe dimensions for unknown media files, return full merged list."""
    to_probe: set[str] = set()
    for step_obj in steps:
        for pg in step_obj.pages:
            to_probe.update(f for f in pg if f not in known)
        if step_obj.cover and step_obj.cover not in known:
            to_probe.add(step_obj.cover)
        to_probe.update(f for f in step_obj.unused if f not in known)

    async def _probe(name: str) -> Media:
        try:
            return await run_sync(
                Media.load,
                trip_dir / name,
                compute_perceptual_hash=True,
                limiter=media_limiter,
            )
        except OSError, ValueError:
            return Media(name=name, width=1920, height=1080)

    probed = await asyncio.gather(*[_probe(f) for f in to_probe])
    merged = dict(known)
    for m in probed:
        merged[m.name] = m
    return list(merged.values())


def _fix_album_covers(
    album: Album,
    all_on_disk: set[str],
    cover_name: str,
    steps: list[StepRead],
) -> None:
    """Ensure chapter cover photos reference files that exist on disk."""
    first_step_cover = next((s.cover for s in steps if s.cover), None)
    cover_fallback = (
        cover_name
        if cover_name in all_on_disk
        else (first_step_cover or next(iter(all_on_disk), ""))
    )
    for chapter in album.chapters:
        for attr in ("front_cover_photo", "back_cover_photo"):
            if getattr(chapter, attr) not in all_on_disk:
                setattr(chapter, attr, cover_fallback)


def _assign_new_steps_to_chapters(album: Album, new_steps: list[StepRead]) -> None:
    if not album.chapters or not new_steps:
        return

    new_step_ids = [step.id for step in sorted(new_steps, key=lambda s: s.timestamp)]
    assigned = {step_id for chapter in album.chapters for step_id in chapter.step_ids}
    missing = [step_id for step_id in new_step_ids if step_id not in assigned]
    if not missing:
        return

    chapters = [
        chapter.model_copy(update={"step_ids": list(chapter.step_ids)})
        for chapter in album.chapters
    ]
    chapters[-1].step_ids = [*chapters[-1].step_ids, *missing]
    album.chapters = chapters


async def _process_new_steps(  # noqa: PLR0913
    http: HttpClients,
    user: User,
    aid: str,
    new_ps_steps: list[PSStep],
    cover_name: str,
    step_out: list[StepRead],
) -> AsyncIterator[PhaseUpdate]:
    """Run full processing (elevations, weather, layouts) for new steps."""
    logger.info(
        "processing.reconcile_new_steps",
        album_id=aid,
        step_count=len(new_ps_steps),
    )
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
                elev_task = tg.create_task(run_elevations(http, new_locs, n_new, queue))
                weather_task = tg.create_task(
                    run_weather(http, new_ps_steps, n_new, queue)
                )
                layout_task = tg.create_task(_fetch())
        finally:
            await queue.put(None)
        return TripResults(
            elevations=elev_task.result(),
            weather_by_idx=weather_task.result(),
            layout_by_idx=layout_task.result(),
            cover_name=cover_name,
            perceptual_hashes_by_name={},
        )

    runner = asyncio.create_task(_phases())
    async for event in drain_queue(runner, queue):
        yield event

    results = await runner
    weathers = [results.weather_by_idx[i] for i in range(n_new)]
    layouts_list = [results.layout_by_idx[i] for i in range(n_new)]
    for ps, elev, wthr, layout in zip(
        new_ps_steps, results.elevations, weathers, layouts_list, strict=True
    ):
        step = build_step(user.id, aid, ps, elev, wthr, layout)
        step_out.append(
            StepRead(
                uid=step.uid,
                aid=step.aid,
                id=step.id,
                name=step.name,
                description=step.description,
                timestamp=step.timestamp,
                timezone_id=step.timezone_id,
                location=step.location,
                elevation=step.elevation,
                weather=step.weather,
                cover=step.cover_media_name,
                pages=layout.pages if layout else [],
                unused=[],
            )
        )


def _step_read_to_rows(step: StepRead) -> list[DbRow]:
    rows: list[DbRow] = [
        Step(
            uid=step.uid,
            aid=step.aid,
            id=step.id,
            name=step.name,
            description=step.description,
            timestamp=step.timestamp,
            timezone_id=step.timezone_id,
            location=step.location,
            elevation=step.elevation,
            weather=step.weather,
            cover_media_name=step.cover,
        )
    ]
    rows.extend(
        StepPageMedia(
            uid=step.uid,
            aid=step.aid,
            step_id=step.id,
            page_index=page_index,
            position_index=position_index,
            media_name=media_name,
        )
        for page_index, page in enumerate(step.pages)
        for position_index, media_name in enumerate(page)
    )
    rows.extend(
        StepUnusedMedia(
            uid=step.uid,
            aid=step.aid,
            step_id=step.id,
            position_index=position_index,
            media_name=media_name,
        )
        for position_index, media_name in enumerate(step.unused)
    )
    return rows


async def reconcile_trip(  # noqa: PLR0913
    http: HttpClients,
    user: User,
    trip_dir: Path,
    album: Album,
    existing_steps: list[StepRead],
    db_out: list[DbRow],
    existing_media_rows: list[AlbumMedia] | None = None,
) -> AsyncIterator[ProcessingEvent]:
    """Reconcile an existing album with re-uploaded data.

    Preserves user edits (page layouts, covers) while adapting to
    changed media. New steps get full processing; existing steps
    get media reconciliation.
    """
    aid = trip_dir.name
    trip, locations = await asyncio.to_thread(load_trip_data, trip_dir)
    logger.info(
        "processing.reconcile_started",
        album_id=aid,
        step_count=trip.step_count,
        existing_step_count=len(existing_steps),
    )

    # Phase 1: Build step->media map BEFORE flattening (concurrent scans)
    scan_results = await asyncio.gather(
        *[asyncio.to_thread(_scan_step_media, trip_dir, ps) for ps in trip.all_steps]
    )
    step_media_map = {
        ps.id: media for ps, media in zip(trip.all_steps, scan_results, strict=True)
    }

    # Phase 2: Flatten media and detect cover
    cover_name = cover_name_from_trip(trip)
    cover_name, _cover_orientation = await prepare_media(trip_dir, cover_name)

    # Phase 3: New steps get full processing
    db_by_step_id = {s.id: s for s in existing_steps}
    new_ps_steps = [ps for ps in trip.all_steps if ps.id not in db_by_step_id]

    new_step_objects: list[StepRead] = []
    if new_ps_steps:
        async for event in _process_new_steps(
            http, user, aid, new_ps_steps, cover_name, new_step_objects
        ):
            yield event

    # Phase 4: Reconcile existing steps
    if existing_media_rows is None:
        existing_media_rows = []
    all_on_disk = {
        normalize_name(f.name)
        for f in trip_dir.iterdir()  # noqa: ASYNC240
        if f.is_file()
    }
    media_by_name: dict[str, Media] = {
        row.name: Media(name=row.name, width=row.width, height=row.height)
        for row in existing_media_rows
    }
    reconciled_steps = [
        _reconcile_step(
            db_by_step_id[ps.id],
            ps,
            step_media_map.get(ps.id, set()),
            all_on_disk,
            media_by_name,
        )
        for ps in trip.all_steps
        if ps.id in db_by_step_id
    ]

    # Phase 5: Probe media dimensions for any new/unknown files
    known_media: dict[str, Media] = {
        row.name: Media(name=row.name, width=row.width, height=row.height)
        for row in existing_media_rows
        if row.name in all_on_disk
    }
    merged_media = await _probe_media(
        trip_dir, [*new_step_objects, *reconciled_steps], known_media
    )
    perceptual_hashes_by_name = {
        row.name: row.perceptual_hashes
        for row in existing_media_rows
        if row.name in all_on_disk and row.perceptual_hashes is not None
    }
    for media in merged_media:
        if media.perceptual_hashes is not None:
            perceptual_hashes_by_name.setdefault(media.name, media.perceptual_hashes)
    perceptual_hashes_by_name.update(
        await run_sync(
            compute_serialized_media_hashes,
            [
                trip_dir / media.name
                for media in merged_media
                if media.name not in perceptual_hashes_by_name
            ],
        )
    )
    album_media = build_album_media_rows(
        user.id,
        aid,
        trip_dir,
        merged_media,
        {row.name: row.upgrade_candidate for row in existing_media_rows},
        perceptual_hashes_by_name,
    )

    # Rebuild segments from GPS data (segments are not persisted across
    # re-uploads; always rebuild from GPS locations).
    all_steps = [*reconciled_steps, *new_step_objects]
    all_steps.sort(key=lambda s: s.timestamp)
    if album.chapters:
        album.chapters[0].title = trip.title
        album.chapters[0].subtitle = trip.subtitle
    _assign_new_steps_to_chapters(album, new_step_objects)
    _fix_album_covers(album, all_on_disk, cover_name, all_steps)

    yield PhaseUpdate(phase="segments", done=0, total=1)
    segments = await asyncio.to_thread(
        build_segment_objects,
        user.id,
        aid,
        all_steps,
        locations,
        trip.all_steps,
    )
    yield PhaseUpdate(phase="segments", done=1, total=1)
    yield count_segments(segments)
    album.maps_ranges = multi_day_hike_ranges(segments)

    db_out.append(album)
    db_out.extend(album_media)
    for step in all_steps:
        db_out.extend(_step_read_to_rows(step))
    db_out.extend(segments)

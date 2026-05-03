from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import zipfile
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

import structlog
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.core.tokens import TokenStore
from app.logic.layout.media import MEDIA_EXTENSIONS
from app.models.album import Album
from app.models.segment import Segment
from app.models.step import Step
from app.models.user import AuthProvider, User

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.get_logger(__name__)

_EXPORT_NAME = "wanderbound-export"
EXPORT_FILENAME = f"{_EXPORT_NAME}.zip"

_EXPORT_TIMEOUT = 600
_PROGRESS_EVERY_N_FILES = 10
_JSON_FILES_PER_ALBUM = 3
_EXCLUDED_USER_FIELDS = {f"{p}_sub" for p in AuthProvider.__args__} | {"has_data"}


class ExportProgress(BaseModel):
    type: Literal["progress"] = "progress"
    files_done: int
    files_total: int


class ExportDone(BaseModel):
    type: Literal["done"] = "done"
    token: str


class ExportError(BaseModel):
    type: Literal["error"] = "error"
    detail: str | None = None


ExportEvent = Annotated[
    ExportProgress | ExportDone | ExportError,
    Field(discriminator="type"),
]

_tokens: TokenStore[Path] = TokenStore(
    dir_name=_EXPORT_NAME,
    ttl=300,
    label="export",
    on_evict=lambda p: p.unlink(missing_ok=True),
)

pop_export_token = _tokens.pop
lifespan = _tokens.lifespan


def _scan_media(trips_folder: Path, album_ids: list[str]) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}
    for aid in album_ids:
        try:
            paths = [
                p
                for p in (trips_folder / aid).iterdir()
                if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS
            ]
        except OSError:
            continue
        if paths:
            result[aid] = paths
    return result


def _write_json(zf: zipfile.ZipFile, arcname: str, data: Any) -> None:
    zf.writestr(arcname, json.dumps(data, ensure_ascii=False, indent=2))


@dataclass
class _ZipSpec:
    dest: Path
    account_data: dict[str, Any]
    albums_data: list[dict[str, Any]]
    media_by_album: dict[str, list[Path]]


def _build_zip(
    spec: _ZipSpec,
    progress_callback: Callable[[int], None],
    stop: threading.Event,
) -> None:
    files_done = 0

    def tick() -> None:
        nonlocal files_done
        files_done += 1
        if files_done % _PROGRESS_EVERY_N_FILES == 0:
            progress_callback(files_done)

    with zipfile.ZipFile(spec.dest, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        _write_json(zf, f"{_EXPORT_NAME}/account.json", spec.account_data)
        tick()

        for album in spec.albums_data:
            if stop.is_set():
                return
            aid: str = album["album"]["id"]
            prefix = f"{_EXPORT_NAME}/albums/{aid}"

            _write_json(zf, f"{prefix}/album.json", album["album"])
            tick()
            _write_json(zf, f"{prefix}/steps.json", album["steps"])
            tick()
            _write_json(zf, f"{prefix}/segments.json", album["segments"])
            tick()

            for fpath in spec.media_by_album.get(aid, ()):
                if stop.is_set():
                    return
                zf.write(fpath, f"{prefix}/media/{fpath.name}", zipfile.ZIP_STORED)
                tick()

    if files_done % _PROGRESS_EVERY_N_FILES != 0:
        progress_callback(files_done)


async def _drain_queue(
    queue: asyncio.Queue[int | Exception | None],
    files_total: int,
) -> AsyncGenerator[ExportEvent]:
    async with asyncio.timeout(_EXPORT_TIMEOUT):
        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            yield ExportProgress(files_done=item, files_total=files_total)


async def _run_zip_thread(
    spec: _ZipSpec,
    files_total: int,
) -> AsyncGenerator[ExportEvent]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[int | Exception | None] = asyncio.Queue()
    stop = threading.Event()

    def on_progress(done: int) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, done)

    def run() -> None:
        try:
            _build_zip(spec, on_progress, stop)
            loop.call_soon_threadsafe(queue.put_nowait, None)
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(queue.put_nowait, exc)

    task = asyncio.create_task(asyncio.to_thread(run))

    try:
        async for event in _drain_queue(queue, files_total):
            yield event

        token = _tokens.store(spec.dest)
        logger.info("export.ready", files_total=files_total)
        yield ExportDone(token=token)
    except Exception:
        logger.exception("export.failed")
        stop.set()
        spec.dest.unlink(missing_ok=True)
        yield ExportError()
    finally:
        if not task.done():
            stop.set()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def export_user_data(
    user: User,
    session: AsyncSession,
) -> AsyncGenerator[ExportEvent]:
    logger.info("export.started", user_id=user.id)

    albums = list((await session.exec(select(Album).where(Album.uid == user.id))).all())
    album_ids_loaded = [a.id for a in albums]

    steps_by_album: dict[str, list[Step]] = {aid: [] for aid in album_ids_loaded}
    for step in (
        await session.exec(
            select(Step)
            .where(Step.uid == user.id, col(Step.aid).in_(album_ids_loaded))
            .order_by(col(Step.timestamp), col(Step.id))
        )
    ).all():
        steps_by_album[step.aid].append(step)

    segments_by_album: dict[str, list[Segment]] = {aid: [] for aid in album_ids_loaded}
    for segment in (
        await session.exec(
            select(Segment)
            .where(Segment.uid == user.id, col(Segment.aid).in_(album_ids_loaded))
            .order_by(col(Segment.start_time))
        )
    ).all():
        segments_by_album[segment.aid].append(segment)

    # Serialize on the event loop - model_dump touches SQLAlchemy descriptors
    # which are not thread-safe, and there's no I/O here (data is pre-loaded).
    albums_data: list[dict[str, Any]] = [
        {
            "album": album.model_dump(mode="json", exclude={"uid", "media"}),
            "steps": [
                s.model_dump(mode="json", exclude={"uid", "aid"})
                for s in steps_by_album[album.id]
            ],
            "segments": [
                s.model_dump(mode="json", exclude={"uid", "aid"})
                for s in segments_by_album[album.id]
            ],
        }
        for album in albums
    ]
    album_ids: list[str] = [a["album"]["id"] for a in albums_data]
    del albums  # release ORM objects
    account_data = user.model_dump(mode="json", exclude=_EXCLUDED_USER_FIELDS)

    trips_folder = user.trips_folder
    media_by_album = await asyncio.to_thread(_scan_media, trips_folder, album_ids)
    media_count = sum(len(v) for v in media_by_album.values())
    files_total = 1 + len(albums_data) * _JSON_FILES_PER_ALBUM + media_count

    yield ExportProgress(files_done=0, files_total=files_total)

    spec = _ZipSpec(
        dest=_tokens.make_dest(".zip"),
        account_data=account_data,
        albums_data=albums_data,
        media_by_album=media_by_album,
    )

    async for event in _run_zip_thread(spec, files_total):
        yield event

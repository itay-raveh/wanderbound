from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path
from typing import Any, Self

import structlog
from dbos import DBOS, SetWorkflowID
from pydantic import BaseModel, Field
from sqlalchemy import func, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.worker_threads import run_sync
from app.logic.media_upgrade.hash_cache import local_hash_cache
from app.logic.media_upgrade.hashes import compute_serialized_media_hashes
from app.models.album_media import AlbumMedia
from app.models.processing import ProcessingOperation

logger = structlog.get_logger(__name__)

MEDIA_HASH_QUEUE = "media-hash-backfill"
_HASH_BATCH_SIZE = 8
_RECONCILIATION_INTERVAL_SECONDS = 60.0


class FileIdentity(BaseModel):
    device: int
    inode: int
    size: int
    modified_ns: int

    @classmethod
    def from_path(cls, path: Path) -> Self:
        stat = path.stat()
        return cls(
            device=stat.st_dev,
            inode=stat.st_ino,
            size=stat.st_size,
            modified_ns=stat.st_mtime_ns,
        )


class MediaHashCandidate(BaseModel):
    uid: int
    aid: str
    name: str
    created_at: datetime
    updated_at: datetime
    byte_size: int
    file: FileIdentity


class CandidateDiscovery(BaseModel):
    candidates: list[MediaHashCandidate] = Field(default_factory=list)
    excluded: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HashBackfillStats(BaseModel):
    hashed: int = 0
    already_completed: int = 0
    stale: int = 0
    failed: int = 0

    def plus(self, other: Self) -> Self:
        return type(self)(
            hashed=self.hashed + other.hashed,
            already_completed=self.already_completed + other.already_completed,
            stale=self.stale + other.stale,
            failed=self.failed + other.failed,
        )


class MediaHashWorkflowPayload(BaseModel):
    uid: int
    aid: str


class MediaHashBackfillTarget(MediaHashWorkflowPayload):
    upload_generation: int
    revision: str


def media_hash_workflow_id(
    uid: int, aid: str, upload_generation: int, revision: str
) -> str:
    return f"media-hash-backfill:{uid}:{aid}:{upload_generation}:{revision}"


def _media_hash_retry_workflow_id(workflow_id: str) -> str:
    return f"{workflow_id}:retry:1"


async def enqueue_media_hash_backfill(
    uid: int, aid: str, upload_generation: int, revision: str
) -> object:
    payload = MediaHashWorkflowPayload(uid=uid, aid=aid).model_dump(mode="json")
    workflow_id = media_hash_workflow_id(uid, aid, upload_generation, revision)
    status = await DBOS.get_workflow_status_async(workflow_id)
    if status is not None and status.status in {
        "ERROR",
        "MAX_RECOVERY_ATTEMPTS_EXCEEDED",
    }:
        retry_workflow_id = _media_hash_retry_workflow_id(workflow_id)
        retry_status = await DBOS.get_workflow_status_async(retry_workflow_id)
        if retry_status is not None:
            return retry_status
        with SetWorkflowID(retry_workflow_id):
            return await DBOS.fork_workflow_async(
                workflow_id,
                0,
                queue_name=MEDIA_HASH_QUEUE,
            )
    with SetWorkflowID(workflow_id):
        handle = await DBOS.enqueue_workflow_async(
            MEDIA_HASH_QUEUE,
            media_hash_backfill_workflow,
            payload,
        )
    logger.info(
        "media_hash.backfill_scheduled",
        user_id=uid,
        album_id=aid,
        upload_generation=upload_generation,
        revision=revision,
        workflow_id=workflow_id,
    )
    return handle


async def missing_media_hash_backfill_targets(
    session: AsyncSession,
) -> list[MediaHashBackfillTarget]:
    missing_albums = (
        await session.exec(
            select(AlbumMedia.uid, AlbumMedia.aid)
            .where(col(AlbumMedia.perceptual_hashes).is_(None))
            .distinct()
            .order_by(col(AlbumMedia.uid), col(AlbumMedia.aid))
        )
    ).all()
    generations = (
        await session.exec(
            select(
                ProcessingOperation.uid,
                func.max(ProcessingOperation.upload_generation),
            )
            .where(col(ProcessingOperation.status) == "succeeded")
            .group_by(col(ProcessingOperation.uid))
        )
    ).all()
    generation_by_uid = dict(generations)
    targets: list[MediaHashBackfillTarget] = []
    for uid, aid in missing_albums:
        revision = await media_hash_backfill_revision(session, uid, aid)
        if revision is None:
            continue
        targets.append(
            MediaHashBackfillTarget(
                uid=uid,
                aid=aid,
                upload_generation=generation_by_uid.get(uid, 0),
                revision=revision,
            )
        )
    return targets


def _revision_for_rows(rows: list[tuple[str, datetime, int]]) -> str:
    digest = hashlib.sha256()
    for name, updated_at, byte_size in rows:
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(updated_at.isoformat().encode())
        digest.update(b"\0")
        digest.update(str(byte_size).encode())
        digest.update(b"\0")
    return digest.hexdigest()[:20]


async def media_hash_backfill_revision(
    session: AsyncSession, uid: int, aid: str
) -> str | None:
    rows = (
        await session.exec(
            select(
                AlbumMedia.name,
                AlbumMedia.updated_at,
                AlbumMedia.byte_size,
                AlbumMedia.perceptual_hashes,
            )
            .where(AlbumMedia.uid == uid, AlbumMedia.aid == aid)
            .order_by(AlbumMedia.name)
        )
    ).all()
    if not any(hashes is None for _, _, _, hashes in rows):
        return None
    return _revision_for_rows(
        [(name, updated_at, byte_size) for name, updated_at, byte_size, _ in rows]
    )


async def reconcile_missing_media_hash_backfills() -> None:
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        targets = await missing_media_hash_backfill_targets(session)
    for target in targets:
        try:
            await enqueue_media_hash_backfill(
                target.uid,
                target.aid,
                target.upload_generation,
                target.revision,
            )
        except Exception as exc:
            logger.exception(
                "media_hash.backfill_reconciliation_failed",
                user_id=target.uid,
                album_id=target.aid,
                upload_generation=target.upload_generation,
                revision=target.revision,
                error_type=type(exc).__name__,
            )


async def media_hash_reconciliation_loop() -> None:
    while True:
        await asyncio.sleep(_RECONCILIATION_INTERVAL_SECONDS)
        try:
            await reconcile_missing_media_hash_backfills()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "media_hash.backfill_periodic_reconciliation_failed",
                error_type=type(exc).__name__,
            )


def _identity_or_none(path: Path) -> FileIdentity | None:
    try:
        return FileIdentity.from_path(path)
    except OSError:
        return None


async def discover_missing_media_hashes(
    session: AsyncSession,
    uid: int,
    aid: str,
    album_dir: Path,
) -> CandidateDiscovery:
    rows = (
        await session.exec(
            select(AlbumMedia)
            .where(AlbumMedia.uid == uid, AlbumMedia.aid == aid)
            .where(col(AlbumMedia.perceptual_hashes).is_(None))
            .order_by(AlbumMedia.name)
        )
    ).all()
    candidates: list[MediaHashCandidate] = []
    excluded = 0
    for row in rows:
        identity = await run_sync(_identity_or_none, album_dir / row.name)
        if identity is None or identity.size != row.byte_size:
            excluded += 1
            continue
        candidates.append(
            MediaHashCandidate(
                uid=row.uid,
                aid=row.aid,
                name=row.name,
                created_at=row.created_at,
                updated_at=row.updated_at,
                byte_size=row.byte_size,
                file=identity,
            )
        )
    return CandidateDiscovery(candidates=candidates, excluded=excluded)


async def _matching_paths(
    album_dir: Path, candidates: list[MediaHashCandidate]
) -> tuple[list[Path], set[str]]:
    paths: list[Path] = []
    stale: set[str] = set()
    for candidate in candidates:
        path = album_dir / candidate.name
        if await run_sync(_identity_or_none, path) != candidate.file:
            stale.add(candidate.name)
        else:
            paths.append(path)
    return paths, stale


async def _persist_hash_if_current(
    session: AsyncSession,
    candidate: MediaHashCandidate,
    hashes: list[str],
) -> bool:
    result = await session.exec(
        update(AlbumMedia)
        .where(
            col(AlbumMedia.uid) == candidate.uid,
            col(AlbumMedia.aid) == candidate.aid,
            col(AlbumMedia.name) == candidate.name,
            col(AlbumMedia.perceptual_hashes).is_(None),
            col(AlbumMedia.created_at) == candidate.created_at,
            col(AlbumMedia.updated_at) == candidate.updated_at,
            col(AlbumMedia.byte_size) == candidate.byte_size,
        )
        .values(perceptual_hashes=hashes)
    )
    return bool(result.rowcount)


async def hash_media_batch(
    session: AsyncSession,
    album_dir: Path,
    candidates: list[MediaHashCandidate],
) -> HashBackfillStats:
    paths, stale_names = await _matching_paths(album_dir, candidates)
    if paths:
        cached_hash = await run_sync(local_hash_cache, album_dir)
        hashes_by_name = await run_sync(
            compute_serialized_media_hashes,
            paths,
            workers=1,
            cached_hash=cached_hash,
        )
    else:
        hashes_by_name = {}
    stats = HashBackfillStats(stale=len(stale_names))
    for candidate in candidates:
        if candidate.name in stale_names:
            continue
        identity = await run_sync(_identity_or_none, album_dir / candidate.name)
        if identity != candidate.file:
            stats.stale += 1
            continue
        hashes = hashes_by_name.get(candidate.name)
        if hashes is None:
            stats.failed += 1
            continue
        if await _persist_hash_if_current(session, candidate, hashes):
            stats.hashed += 1
            continue
        current_hash = await session.scalar(
            select(AlbumMedia.perceptual_hashes).where(
                AlbumMedia.uid == candidate.uid,
                AlbumMedia.aid == candidate.aid,
                AlbumMedia.name == candidate.name,
            )
        )
        if current_hash is None:
            stats.stale += 1
        else:
            stats.already_completed += 1
    await session.commit()
    return stats


def _album_dir(payload: MediaHashWorkflowPayload) -> Path:
    return get_settings().USERS_FOLDER / str(payload.uid) / "trip" / payload.aid


@DBOS.step(retries_allowed=True, max_attempts=3)
async def discover_media_hash_candidates_step(
    payload: dict[str, Any],
) -> dict[str, Any]:
    params = MediaHashWorkflowPayload.model_validate(payload)
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        discovery = await discover_missing_media_hashes(
            session, params.uid, params.aid, _album_dir(params)
        )
    logger.info(
        "media_hash.backfill_started",
        user_id=params.uid,
        album_id=params.aid,
        candidate_count=len(discovery.candidates),
        excluded_count=discovery.excluded,
    )
    return discovery.model_dump(mode="json")


@DBOS.step(retries_allowed=True, max_attempts=3)
async def hash_media_batch_step(
    payload: dict[str, Any], candidates: list[dict[str, Any]]
) -> dict[str, int]:
    params = MediaHashWorkflowPayload.model_validate(payload)
    parsed = [MediaHashCandidate.model_validate(item) for item in candidates]
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        stats = await hash_media_batch(session, _album_dir(params), parsed)
    logger.info(
        "media_hash.backfill_batch_completed",
        user_id=params.uid,
        album_id=params.aid,
        **stats.model_dump(),
    )
    return stats.model_dump()


@DBOS.step(retries_allowed=True, max_attempts=3)
async def complete_media_hash_backfill_step(
    payload: dict[str, Any],
    started_at: str,
    candidate_count: int,
    excluded: int,
    stats: dict[str, int],
) -> dict[str, int]:
    params = MediaHashWorkflowPayload.model_validate(payload)
    totals = HashBackfillStats.model_validate(stats)
    duration_seconds = (
        datetime.now(UTC) - datetime.fromisoformat(started_at)
    ).total_seconds()
    logger.info(
        "media_hash.backfill_completed",
        user_id=params.uid,
        album_id=params.aid,
        candidate_count=candidate_count,
        excluded_count=excluded,
        duration_seconds=duration_seconds,
        **totals.model_dump(),
    )
    return totals.model_dump()


@DBOS.workflow(name="media_hash.backfill")
async def media_hash_backfill_workflow(payload: dict[str, Any]) -> dict[str, int]:
    discovery = CandidateDiscovery.model_validate(
        await discover_media_hash_candidates_step(payload)
    )
    totals = HashBackfillStats()
    for batch in batched(discovery.candidates, _HASH_BATCH_SIZE, strict=False):
        result = await hash_media_batch_step(
            payload,
            [candidate.model_dump(mode="json") for candidate in batch],
        )
        totals = totals.plus(HashBackfillStats.model_validate(result))
    return await complete_media_hash_backfill_step(
        payload,
        discovery.started_at.isoformat(),
        len(discovery.candidates),
        discovery.excluded,
        totals.model_dump(),
    )

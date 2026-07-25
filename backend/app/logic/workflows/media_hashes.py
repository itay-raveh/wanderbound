from __future__ import annotations

import asyncio
import hashlib
from collections import Counter
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path
from typing import Any, NamedTuple

import structlog
from dbos import DBOS, SetWorkflowID
from pydantic import BaseModel
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
_HASH_BATCH_SIZE = 32
_RECONCILIATION_INTERVAL_SECONDS = 60.0


class FileIdentity(NamedTuple):
    device: int
    inode: int
    size: int
    modified_ns: int


class MediaHashCandidate(NamedTuple):
    name: str
    created_at: datetime
    updated_at: datetime
    byte_size: int
    file: FileIdentity


class HashBackfillStats(BaseModel):
    hashed: int = 0
    already_completed: int = 0
    stale: int = 0
    failed: int = 0


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
            .where(
                col(AlbumMedia.perceptual_hashes).is_(None),
                AlbumMedia.kind == "photo",
            )
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
        if revision is not None:
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
            .where(AlbumMedia.kind == "photo")
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


def _file_identity(path: Path) -> FileIdentity:
    stat = path.stat()
    return FileIdentity(
        stat.st_dev,
        stat.st_ino,
        stat.st_size,
        stat.st_mtime_ns,
    )


def _identity_or_none(path: Path) -> FileIdentity | None:
    try:
        return _file_identity(path)
    except OSError:
        return None


def _snapshot_candidates(
    album_dir: Path,
    rows: list[tuple[str, datetime, datetime, int]],
) -> tuple[list[MediaHashCandidate], int]:
    candidates: list[MediaHashCandidate] = []
    excluded = 0
    for name, created_at, updated_at, byte_size in rows:
        identity = _identity_or_none(album_dir / name)
        if identity is None or identity.size != byte_size:
            excluded += 1
        else:
            candidates.append(
                MediaHashCandidate(
                    name,
                    created_at,
                    updated_at,
                    byte_size,
                    identity,
                )
            )
    return candidates, excluded


async def _discover_candidates(
    uid: int,
    aid: str,
    album_dir: Path,
) -> tuple[list[MediaHashCandidate], int]:
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        rows = list(
            (
                await session.exec(
                    select(
                        AlbumMedia.name,
                        AlbumMedia.created_at,
                        AlbumMedia.updated_at,
                        AlbumMedia.byte_size,
                    )
                    .where(AlbumMedia.uid == uid, AlbumMedia.aid == aid)
                    .where(
                        col(AlbumMedia.perceptual_hashes).is_(None),
                        AlbumMedia.kind == "photo",
                    )
                    .order_by(AlbumMedia.name)
                )
            ).all()
        )
    return await run_sync(_snapshot_candidates, album_dir, rows)


async def _persist_hash_if_current(
    session: AsyncSession,
    uid: int,
    aid: str,
    candidate: MediaHashCandidate,
    hashes: list[str],
) -> bool:
    result = await session.exec(
        update(AlbumMedia)
        .where(
            col(AlbumMedia.uid) == uid,
            col(AlbumMedia.aid) == aid,
            col(AlbumMedia.name) == candidate.name,
            col(AlbumMedia.perceptual_hashes).is_(None),
            col(AlbumMedia.created_at) == candidate.created_at,
            col(AlbumMedia.updated_at) == candidate.updated_at,
            col(AlbumMedia.byte_size) == candidate.byte_size,
        )
        .values(perceptual_hashes=hashes)
    )
    return bool(result.rowcount)


def _current_candidates(
    album_dir: Path,
    candidates: list[MediaHashCandidate],
) -> list[MediaHashCandidate]:
    return [
        candidate
        for candidate in candidates
        if _identity_or_none(album_dir / candidate.name) == candidate.file
    ]


def _candidate_identities(
    album_dir: Path,
    candidates: list[MediaHashCandidate],
) -> dict[str, FileIdentity | None]:
    return {
        candidate.name: _identity_or_none(album_dir / candidate.name)
        for candidate in candidates
    }


async def persist_media_hash_batch(
    session: AsyncSession,
    payload: MediaHashWorkflowPayload,
    album_dir: Path,
    candidates: list[MediaHashCandidate],
    hashes_by_name: dict[str, list[str]],
) -> HashBackfillStats:
    identities = await run_sync(_candidate_identities, album_dir, candidates)
    stats = HashBackfillStats()
    for candidate in candidates:
        if identities[candidate.name] != candidate.file:
            stats.stale += 1
            continue
        hashes = hashes_by_name.get(candidate.name)
        if hashes is None:
            stats.failed += 1
            continue
        if await _persist_hash_if_current(
            session, payload.uid, payload.aid, candidate, hashes
        ):
            stats.hashed += 1
            continue
        current_hash = await session.scalar(
            select(AlbumMedia.perceptual_hashes).where(
                AlbumMedia.uid == payload.uid,
                AlbumMedia.aid == payload.aid,
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


async def backfill_media_hashes(
    uid: int,
    aid: str,
    album_dir: Path,
) -> HashBackfillStats:
    started_at = datetime.now(UTC)
    payload = MediaHashWorkflowPayload(uid=uid, aid=aid)
    candidates, excluded = await _discover_candidates(uid, aid, album_dir)
    logger.info(
        "media_hash.backfill_started",
        user_id=uid,
        album_id=aid,
        candidate_count=len(candidates),
        excluded_count=excluded,
    )

    totals: Counter[str] = Counter()
    current = await run_sync(_current_candidates, album_dir, candidates)
    totals["stale"] = len(candidates) - len(current)
    hashes_by_name: dict[str, list[str]] = {}
    if current:
        cached_hash = await run_sync(local_hash_cache, album_dir)
        hashes_by_name = await run_sync(
            compute_serialized_media_hashes,
            [album_dir / candidate.name for candidate in current],
            cached_hash=cached_hash,
        )

    for batch in batched(current, _HASH_BATCH_SIZE, strict=False):
        async with AsyncSession(get_engine(), expire_on_commit=False) as session:
            stats = await persist_media_hash_batch(
                session,
                payload,
                album_dir,
                list(batch),
                hashes_by_name,
            )
        totals.update(stats.model_dump())

    result = HashBackfillStats.model_validate(totals)
    logger.info(
        "media_hash.backfill_completed",
        user_id=uid,
        album_id=aid,
        candidate_count=len(candidates),
        excluded_count=excluded,
        duration_seconds=(datetime.now(UTC) - started_at).total_seconds(),
        **result.model_dump(),
    )
    return result


@DBOS.step(retries_allowed=True, max_attempts=3)
async def backfill_media_hashes_step(payload: dict[str, Any]) -> dict[str, int]:
    params = MediaHashWorkflowPayload.model_validate(payload)
    result = await backfill_media_hashes(
        params.uid,
        params.aid,
        _album_dir(params),
    )
    return result.model_dump()


@DBOS.workflow(name="media_hash.backfill")
async def media_hash_backfill_workflow(payload: dict[str, Any]) -> dict[str, int]:
    return await backfill_media_hashes_step(payload)

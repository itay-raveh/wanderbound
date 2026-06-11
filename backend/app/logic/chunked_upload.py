from __future__ import annotations

import asyncio
import contextlib
import secrets
import shutil
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

import anyio
import structlog
from sqlmodel import col, select

from app.core.config import get_settings
from app.core.observability import start_span
from app.models.processing import UploadSession

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.get_logger(__name__)

_UPLOAD_TTL = 3600  # 1 hour
_CHUNK_LIMIT = 80 * 1024 * 1024 + 1024  # 80 MiB + 1 KiB margin
_FLUSH_AT = 1024 * 1024  # flush buffer to disk every 1 MiB
_CLEANUP_INTERVAL = 60
_UPLOAD_ID_CHARS = frozenset(
    "-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _stream_to_file(path: Path, stream: AsyncIterator[bytes], index: int) -> int:
    """Drain *stream* into *path*, flushing every _FLUSH_AT bytes. Returns total."""
    written = 0
    async with await anyio.open_file(path, "wb") as f:
        buf = bytearray()
        async for piece in stream:
            written += len(piece)
            if written > _CHUNK_LIMIT:
                msg = f"Chunk {index} exceeds {_CHUNK_LIMIT} bytes"
                raise ValueError(msg)
            buf.extend(piece)
            if len(buf) >= _FLUSH_AT:
                await f.write(bytes(buf))
                buf.clear()
        if buf:
            await f.write(bytes(buf))
    return written


class UploadStore:
    """Manages in-progress chunked uploads with DB-backed session metadata."""

    def __init__(
        self, base: Path | None = None, *, cleanup_interval: float = _CLEANUP_INTERVAL
    ) -> None:
        self._base_override = base
        self._cleanup_interval = cleanup_interval
        self._base: Path  # resolved in lifespan()
        self._locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        self._base = (
            self._base_override or get_settings().DATA_FOLDER / "chunked-uploads"
        )
        self._base.mkdir(parents=True, exist_ok=True)
        yield

    async def create(self, session: AsyncSession, max_bytes: int, *, owner: str) -> str:
        """Start a new upload session. Returns an opaque upload_id."""
        upload_id = secrets.token_urlsafe()
        upload_dir = self._upload_dir(upload_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        row = UploadSession(
            upload_id=upload_id,
            max_bytes=max_bytes,
            max_chunks=max_bytes // _CHUNK_LIMIT + 2,
            owner=owner,
            accumulated_bytes=0,
            chunks_written=[],
            expires_at=_now() + timedelta(seconds=_UPLOAD_TTL),
        )
        session.add(row)
        await session.flush()
        logger.info("upload.session_created", upload_id_prefix=upload_id[:8])
        return upload_id

    async def write_chunk_stream(
        self,
        session: AsyncSession,
        upload_id: str,
        index: int,
        stream: AsyncIterator[bytes],
    ) -> None:
        """Stream a chunk body to disk without buffering it in memory."""
        upload_dir = await self._existing_upload_dir(session, upload_id)
        if not 0 <= index < 10_000:
            msg = f"Chunk index out of range: {index}"
            raise ValueError(msg)

        lock = self._locks.setdefault(upload_id, asyncio.Lock())
        async with lock:
            row = await self._get_session_for_update(session, upload_id)
            chunks_written = set(row.chunks_written)
            if index not in chunks_written and len(chunks_written) >= row.max_chunks:
                msg = f"Too many chunks (limit {row.max_chunks})"
                raise ValueError(msg)

            tmp_path = upload_dir / f"{index:04d}.{secrets.token_hex(8)}.part"
            try:
                written = await _stream_to_file(tmp_path, stream, index)
                await self._commit_stream_chunk(session, row, index, tmp_path, written)
            except Exception:
                if not upload_dir.exists():
                    raise KeyError(upload_id) from None
                raise
            finally:
                with contextlib.suppress(OSError):
                    tmp_path.unlink(missing_ok=True)

    async def _commit_stream_chunk(
        self,
        session: AsyncSession,
        row: UploadSession,
        index: int,
        tmp_path: Path,
        written: int,
    ) -> None:
        upload_dir = self._upload_dir(row.upload_id)
        final_path = upload_dir / f"{index:04d}"
        chunks_written = set(row.chunks_written)
        effective = row.accumulated_bytes
        if index in chunks_written:
            with contextlib.suppress(OSError):
                effective -= final_path.stat().st_size

        if effective + written > row.max_bytes:
            raise OverflowError("Upload exceeds maximum size")

        await anyio.Path(tmp_path).rename(final_path)
        chunks_written.add(index)
        row.accumulated_bytes = effective + written
        row.chunks_written = sorted(chunks_written)
        row.updated_at = _now()
        session.add(row)
        await session.flush()

    async def assemble(
        self, session: AsyncSession, upload_id: str, *, owner: str
    ) -> tuple[BinaryIO, Path]:
        """Concatenate all chunks into a single seekable file."""
        upload_dir = await self._existing_upload_dir(session, upload_id)
        row = await self._get_session_for_update(session, upload_id)
        if row.owner != owner:
            raise PermissionError("Upload session belongs to a different user")

        chunks_written = set(row.chunks_written)
        if not chunks_written:
            await self._delete_row_and_dir(session, row)
            msg = "No chunks uploaded"
            raise ValueError(msg)

        expected = set(range(len(chunks_written)))
        if chunks_written != expected:
            await self._delete_row_and_dir(session, row)
            msg = "Chunks are not contiguous from 0"
            raise ValueError(msg)

        chunks = [upload_dir / f"{index:04d}" for index in sorted(chunks_written)]
        assembled = upload_dir / "assembled.zip"
        with start_span(
            "upload.assemble",
            "Assemble chunked upload",
            **{
                "app.workflow": "upload",
                "chunk.count": len(chunks),
                "size.bytes": row.accumulated_bytes,
            },
        ):
            with assembled.open("wb") as out:
                for chunk_path in chunks:
                    with chunk_path.open("rb") as src:
                        shutil.copyfileobj(src, out)

            for chunk_path in chunks:
                chunk_path.unlink()
            await session.delete(row)
            await session.flush()

        try:
            return assembled.open("rb"), upload_dir
        except OSError:
            shutil.rmtree(upload_dir, ignore_errors=True)
            raise

    async def cleanup_expired(self, session: AsyncSession) -> None:
        rows = (
            await session.exec(
                select(UploadSession).where(col(UploadSession.expires_at) <= _now())
            )
        ).all()
        for row in rows:
            await self._delete_row_and_dir(session, row)

    async def _evict(self, session: AsyncSession, upload_id: str) -> None:
        row = await session.get(UploadSession, upload_id)
        if row is None:
            return
        await self._delete_row_and_dir(session, row)
        logger.info("upload.session_expired", upload_id_prefix=upload_id[:8])

    async def _delete_row_and_dir(
        self, session: AsyncSession, row: UploadSession
    ) -> None:
        shutil.rmtree(self._upload_dir(row.upload_id), ignore_errors=True)
        await session.delete(row)
        await session.flush()

    async def _existing_upload_dir(self, session: AsyncSession, upload_id: str) -> Path:
        upload_dir = self._upload_dir(upload_id)
        row = await session.get(UploadSession, upload_id)
        if row is None or not upload_dir.exists() or _aware(row.expires_at) <= _now():
            if row is not None:
                await self._delete_row_and_dir(session, row)
            raise KeyError(upload_id)
        return upload_dir

    async def _get_session_for_update(
        self, session: AsyncSession, upload_id: str
    ) -> UploadSession:
        result = await session.exec(
            select(UploadSession)
            .where(col(UploadSession.upload_id) == upload_id)
            .with_for_update()
        )
        row = result.one_or_none()
        if row is None:
            raise KeyError(upload_id)
        return row

    def _upload_dir(self, upload_id: str) -> Path:
        if not upload_id or any(char not in _UPLOAD_ID_CHARS for char in upload_id):
            raise KeyError(upload_id)
        return self._base / upload_id


upload_store = UploadStore()

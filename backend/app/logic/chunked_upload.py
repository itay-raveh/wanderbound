import asyncio
import contextlib
import secrets
import shutil
import threading
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import anyio
import structlog

from app.core.config import get_settings
from app.core.observability import start_span

logger = structlog.get_logger(__name__)

_UPLOAD_TTL = 3600  # 1 hour
_CHUNK_LIMIT = 80 * 1024 * 1024 + 1024  # 80 MiB + 1 KiB margin
_FLUSH_AT = 1024 * 1024  # flush buffer to disk every 1 MiB


@dataclass
class _Session:
    dir: Path
    timer: asyncio.TimerHandle
    max_bytes: int
    max_chunks: int
    owner: str
    lock: threading.Lock = field(default_factory=threading.Lock)
    accumulated_bytes: int = 0
    chunks_written: set[int] = field(default_factory=set)


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
    """Manages in-progress chunked uploads with automatic TTL eviction."""

    def __init__(self, base: Path | None = None) -> None:
        self._base_override = base
        self._base: Path  # resolved in lifespan()
        self._sessions: dict[str, _Session] = {}

    # -- lifecycle --------------------------------------------------------

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        self._base = (
            self._base_override or get_settings().DATA_FOLDER / "chunked-uploads"
        )
        shutil.rmtree(self._base, ignore_errors=True)
        self._base.mkdir(parents=True, exist_ok=True)
        try:
            yield
        finally:
            for session in self._sessions.values():
                session.timer.cancel()
                shutil.rmtree(session.dir, ignore_errors=True)
            self._sessions.clear()

    # -- public API -------------------------------------------------------

    def create(self, max_bytes: int, *, owner: str) -> str:
        """Start a new upload session. Returns an opaque upload_id."""
        upload_id = secrets.token_urlsafe()
        upload_dir = self._base / secrets.token_hex(16)
        upload_dir.mkdir(parents=True, exist_ok=True)
        timer = asyncio.get_running_loop().call_later(
            _UPLOAD_TTL, self._evict, upload_id
        )
        max_chunks = max_bytes // _CHUNK_LIMIT + 2  # +2 for rounding and final runt
        self._sessions[upload_id] = _Session(
            dir=upload_dir,
            timer=timer,
            max_bytes=max_bytes,
            max_chunks=max_chunks,
            owner=owner,
        )
        logger.info("upload.session_created", upload_id_prefix=upload_id[:8])
        return upload_id

    async def write_chunk_stream(
        self, upload_id: str, index: int, stream: AsyncIterator[bytes]
    ) -> None:
        """Stream a chunk body to disk without buffering it in memory.

        Raises KeyError if session not found, ValueError on bad input,
        OverflowError if accumulated size exceeds max_bytes.
        """
        session = self._sessions.get(upload_id)
        if session is None:
            raise KeyError(upload_id)
        if not 0 <= index < 10_000:
            msg = f"Chunk index out of range: {index}"
            raise ValueError(msg)

        # Pre-check the chunk-count limit for *new* indices (under lock).
        with session.lock:
            if (
                index not in session.chunks_written
                and len(session.chunks_written) >= session.max_chunks
            ):
                msg = f"Too many chunks (limit {session.max_chunks})"
                raise ValueError(msg)

        tmp_path = session.dir / f"{index:04d}.{secrets.token_hex(8)}.part"
        try:
            written = await _stream_to_file(tmp_path, stream, index)
            self._commit_stream_chunk(session, index, tmp_path, written)
        except Exception:
            if upload_id not in self._sessions:
                raise KeyError(upload_id) from None
            raise
        finally:
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)

    @staticmethod
    def _commit_stream_chunk(
        session: _Session, index: int, tmp_path: Path, written: int
    ) -> None:
        """Atomically promote tmp_path to the final chunk path under the lock."""
        final_path = session.dir / f"{index:04d}"
        with session.lock:
            effective = session.accumulated_bytes
            if index in session.chunks_written:
                with contextlib.suppress(OSError):
                    effective -= final_path.stat().st_size

            if effective + written > session.max_bytes:
                raise OverflowError("Upload exceeds maximum size")

            tmp_path.rename(final_path)
            session.accumulated_bytes = effective + written
            session.chunks_written.add(index)

    def assemble(self, upload_id: str, *, owner: str) -> tuple[BinaryIO, Path]:
        """Concatenate all chunks into a single seekable file.

        Returns ``(file, session_dir)``.  The caller owns both and must
        clean them up (close the file, then ``shutil.rmtree`` the dir).

        Raises PermissionError if *owner* doesn't match the session creator.
        """
        session = self._sessions.get(upload_id)
        if session is None:
            raise KeyError(upload_id)
        if session.owner != owner:
            raise PermissionError("Upload session belongs to a different user")
        self._sessions.pop(upload_id)
        session.timer.cancel()

        if not session.chunks_written:
            shutil.rmtree(session.dir, ignore_errors=True)
            msg = "No chunks uploaded"
            raise ValueError(msg)

        expected = set(range(len(session.chunks_written)))
        if session.chunks_written != expected:
            shutil.rmtree(session.dir, ignore_errors=True)
            msg = "Chunks are not contiguous from 0"
            raise ValueError(msg)

        chunks = sorted(session.dir.glob("[0-9][0-9][0-9][0-9]"))
        assembled = session.dir / "assembled.zip"
        with start_span(
            "upload.assemble",
            "Assemble chunked upload",
            **{
                "app.workflow": "upload",
                "chunk.count": len(chunks),
                "size.bytes": session.accumulated_bytes,
            },
        ):
            with assembled.open("wb") as out:
                for chunk_path in chunks:
                    with chunk_path.open("rb") as src:
                        shutil.copyfileobj(src, out)

            for chunk_path in chunks:
                chunk_path.unlink()

        try:
            return assembled.open("rb"), session.dir
        except OSError:
            shutil.rmtree(session.dir, ignore_errors=True)
            raise

    # -- internals --------------------------------------------------------

    def _evict(self, upload_id: str) -> None:
        session = self._sessions.pop(upload_id, None)
        if session is None:
            return
        asyncio.get_running_loop().run_in_executor(
            None, lambda: shutil.rmtree(session.dir, ignore_errors=True)
        )
        logger.info("upload.session_expired", upload_id_prefix=upload_id[:8])


upload_store = UploadStore()

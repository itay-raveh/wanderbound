import asyncio
import contextlib
import logging
import secrets
import shutil
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger(__name__)

_UPLOAD_TTL = 3600  # 1 hour
_CHUNK_LIMIT = 80 * 1024 * 1024 + 1024  # 80 MiB + 1 KiB margin


@dataclass
class _Session:
    dir: Path
    timer: asyncio.TimerHandle
    max_bytes: int
    max_chunks: int
    owner: str
    accumulated_bytes: int = 0
    chunks_written: set[int] = field(default_factory=set)


class UploadStore:
    """Manages in-progress chunked uploads with automatic TTL eviction."""

    def __init__(self) -> None:
        self._base = Path(tempfile.gettempdir()) / "chunked-uploads"
        self._sessions: dict[str, _Session] = {}

    # -- lifecycle --------------------------------------------------------

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
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
        logger.info("Upload session %s created", upload_id[:8])
        return upload_id

    def write_chunk(self, upload_id: str, index: int, data: bytes) -> None:
        """Write a chunk to the session directory.

        Raises KeyError if session not found, ValueError on bad input,
        OverflowError if accumulated size exceeds max_bytes.
        """
        session = self._sessions.get(upload_id)
        if session is None:
            raise KeyError(upload_id)
        if not 0 <= index < 10_000:
            msg = f"Chunk index out of range: {index}"
            raise ValueError(msg)
        if len(data) > _CHUNK_LIMIT:
            msg = f"Chunk {index} is {len(data)} bytes (limit {_CHUNK_LIMIT})"
            raise ValueError(msg)

        # Deduct old size before overflow check so retries aren't falsely rejected
        effective = session.accumulated_bytes
        if index in session.chunks_written:
            with contextlib.suppress(OSError):
                effective -= (session.dir / f"{index:04d}").stat().st_size
        elif len(session.chunks_written) >= session.max_chunks:
            msg = f"Too many chunks (limit {session.max_chunks})"
            raise ValueError(msg)

        if effective + len(data) > session.max_bytes:
            raise OverflowError("Upload exceeds maximum size")

        chunk_path = session.dir / f"{index:04d}"
        chunk_path.write_bytes(data)
        session.accumulated_bytes = effective + len(data)
        session.chunks_written.add(index)

    def assemble(self, upload_id: str, *, owner: str) -> BinaryIO:
        """Concatenate all chunks into a single seekable file.

        Pops the session from the store. The caller owns the returned file
        and the session directory (must clean up both).

        Raises PermissionError if *owner* doesn't match the session creator.
        """
        session = self._sessions.get(upload_id)
        if session is None:
            raise KeyError(upload_id)
        if session.owner != owner:
            raise PermissionError("Upload session belongs to a different user")
        self._sessions.pop(upload_id)
        session.timer.cancel()

        chunks = sorted(session.dir.glob("[0-9]*"))
        if not chunks:
            shutil.rmtree(session.dir, ignore_errors=True)
            msg = "No chunks uploaded"
            raise ValueError(msg)

        assembled = session.dir / "assembled.zip"
        with assembled.open("wb") as out:
            for chunk_path in chunks:
                with chunk_path.open("rb") as src:
                    shutil.copyfileobj(src, out)

        # Remove individual chunk files, keep only the assembled file
        for chunk_path in chunks:
            chunk_path.unlink()

        return assembled.open("rb")

    # -- internals --------------------------------------------------------

    def _evict(self, upload_id: str) -> None:
        session = self._sessions.pop(upload_id, None)
        if session is None:
            return
        asyncio.get_running_loop().run_in_executor(
            None, lambda: shutil.rmtree(session.dir, ignore_errors=True)
        )
        logger.info("Expired upload session %s", upload_id[:8])


upload_store = UploadStore()

import asyncio
import contextlib
import fcntl
import json
import secrets
import shutil
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from time import time
from typing import BinaryIO, TypedDict

import anyio
import structlog

from app.core.config import get_settings
from app.core.observability import start_span

logger = structlog.get_logger(__name__)

_UPLOAD_TTL = 3600  # 1 hour
_CHUNK_LIMIT = 80 * 1024 * 1024 + 1024  # 80 MiB + 1 KiB margin
_FLUSH_AT = 1024 * 1024  # flush buffer to disk every 1 MiB
_MANIFEST_NAME = "upload.json"
_LOCK_NAME = "upload.lock"
_UPLOAD_ID_CHARS = frozenset(
    "-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)


class _Manifest(TypedDict):
    max_bytes: int
    max_chunks: int
    owner: str
    accumulated_bytes: int
    chunks_written: list[int]
    expires_at: float


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

    # -- lifecycle --------------------------------------------------------

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        self._base = (
            self._base_override or get_settings().DATA_FOLDER / "chunked-uploads"
        )
        self._base.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._cleanup_expired)
        yield

    # -- public API -------------------------------------------------------

    def create(self, max_bytes: int, *, owner: str) -> str:
        """Start a new upload session. Returns an opaque upload_id."""
        upload_id = secrets.token_urlsafe()
        upload_dir = self._upload_dir(upload_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        max_chunks = max_bytes // _CHUNK_LIMIT + 2  # +2 for rounding and final runt
        self._write_manifest(
            upload_dir,
            {
                "max_bytes": max_bytes,
                "max_chunks": max_chunks,
                "owner": owner,
                "accumulated_bytes": 0,
                "chunks_written": [],
                "expires_at": time() + _UPLOAD_TTL,
            },
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
        upload_dir = self._existing_upload_dir(upload_id)
        if not 0 <= index < 10_000:
            msg = f"Chunk index out of range: {index}"
            raise ValueError(msg)

        with self._upload_lock(upload_dir):
            manifest = self._read_manifest(upload_dir)
            chunks_written = set(manifest["chunks_written"])
            if (
                index not in chunks_written
                and len(chunks_written) >= manifest["max_chunks"]
            ):
                msg = f"Too many chunks (limit {manifest['max_chunks']})"
                raise ValueError(msg)

        tmp_path = upload_dir / f"{index:04d}.{secrets.token_hex(8)}.part"
        try:
            written = await _stream_to_file(tmp_path, stream, index)
            with self._upload_lock(upload_dir):
                self._commit_stream_chunk(upload_dir, index, tmp_path, written)
        except Exception:
            if not upload_dir.exists():
                raise KeyError(upload_id) from None
            raise
        finally:
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)

    def _commit_stream_chunk(
        self, upload_dir: Path, index: int, tmp_path: Path, written: int
    ) -> None:
        """Atomically promote tmp_path to the final chunk path under the lock."""
        manifest = self._read_manifest(upload_dir)
        chunks_written = set(manifest["chunks_written"])
        final_path = upload_dir / f"{index:04d}"
        effective = manifest["accumulated_bytes"]
        if index in chunks_written:
            with contextlib.suppress(OSError):
                effective -= final_path.stat().st_size

        if effective + written > manifest["max_bytes"]:
            raise OverflowError("Upload exceeds maximum size")

        tmp_path.rename(final_path)
        manifest["accumulated_bytes"] = effective + written
        chunks_written.add(index)
        manifest["chunks_written"] = sorted(chunks_written)
        self._write_manifest(upload_dir, manifest)

    def assemble(self, upload_id: str, *, owner: str) -> tuple[BinaryIO, Path]:
        """Concatenate all chunks into a single seekable file.

        Returns ``(file, session_dir)``.  The caller owns both and must
        clean them up (close the file, then ``shutil.rmtree`` the dir).

        Raises PermissionError if *owner* doesn't match the session creator.
        """
        upload_dir = self._existing_upload_dir(upload_id)
        with self._upload_lock(upload_dir):
            manifest = self._read_manifest(upload_dir)
            if manifest["owner"] != owner:
                raise PermissionError("Upload session belongs to a different user")

            chunks_written = set(manifest["chunks_written"])
            if not chunks_written:
                shutil.rmtree(upload_dir, ignore_errors=True)
                msg = "No chunks uploaded"
                raise ValueError(msg)

            expected = set(range(len(chunks_written)))
            if chunks_written != expected:
                shutil.rmtree(upload_dir, ignore_errors=True)
                msg = "Chunks are not contiguous from 0"
                raise ValueError(msg)

            chunks = sorted(upload_dir.glob("[0-9][0-9][0-9][0-9]"))
            assembled = upload_dir / "assembled.zip"
            with start_span(
                "upload.assemble",
                "Assemble chunked upload",
                **{
                    "app.workflow": "upload",
                    "chunk.count": len(chunks),
                    "size.bytes": manifest["accumulated_bytes"],
                },
            ):
                with assembled.open("wb") as out:
                    for chunk_path in chunks:
                        with chunk_path.open("rb") as src:
                            shutil.copyfileobj(src, out)

                for chunk_path in chunks:
                    chunk_path.unlink()
                (upload_dir / _MANIFEST_NAME).unlink(missing_ok=True)

        try:
            return assembled.open("rb"), upload_dir
        except OSError:
            shutil.rmtree(upload_dir, ignore_errors=True)
            raise

    # -- internals --------------------------------------------------------

    def _evict(self, upload_id: str) -> None:
        upload_dir = self._upload_dir(upload_id)
        if not upload_dir.exists():
            return
        shutil.rmtree(upload_dir, ignore_errors=True)
        logger.info("upload.session_expired", upload_id_prefix=upload_id[:8])

    def _cleanup_expired(self) -> None:
        now = time()
        for upload_dir in self._base.iterdir():
            if not upload_dir.is_dir():
                continue
            with contextlib.suppress(KeyError, OSError):
                manifest = self._read_manifest(upload_dir)
                if manifest["expires_at"] < now:
                    shutil.rmtree(upload_dir, ignore_errors=True)

    def _upload_dir(self, upload_id: str) -> Path:
        if not upload_id or any(char not in _UPLOAD_ID_CHARS for char in upload_id):
            raise KeyError(upload_id)
        return self._base / upload_id

    def _existing_upload_dir(self, upload_id: str) -> Path:
        upload_dir = self._upload_dir(upload_id)
        if not (upload_dir / _MANIFEST_NAME).exists():
            raise KeyError(upload_id)
        return upload_dir

    @contextlib.contextmanager
    def _upload_lock(self, upload_dir: Path) -> Iterator[None]:
        try:
            lock_file = (upload_dir / _LOCK_NAME).open("a+b")
        except OSError as exc:
            raise KeyError(upload_dir.name) from exc
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()

    @staticmethod
    def _read_manifest(upload_dir: Path) -> _Manifest:
        try:
            with (upload_dir / _MANIFEST_NAME).open("rb") as f:
                data = json.load(f)
        except OSError as exc:
            raise KeyError(upload_dir.name) from exc
        return _Manifest(
            max_bytes=int(data["max_bytes"]),
            max_chunks=int(data["max_chunks"]),
            owner=str(data["owner"]),
            accumulated_bytes=int(data["accumulated_bytes"]),
            chunks_written=[int(index) for index in data["chunks_written"]],
            expires_at=float(data["expires_at"]),
        )

    @staticmethod
    def _write_manifest(upload_dir: Path, manifest: _Manifest) -> None:
        tmp_path = upload_dir / f"{_MANIFEST_NAME}.{secrets.token_hex(8)}.tmp"
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, sort_keys=True)
        tmp_path.replace(upload_dir / _MANIFEST_NAME)


upload_store = UploadStore()

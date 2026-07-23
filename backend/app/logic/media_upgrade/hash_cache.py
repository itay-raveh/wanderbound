"""Persistent perceptual-hash cache for local album media."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import imagehash
import structlog

from .phash_matching import MediaHash

logger = structlog.get_logger(__name__)

_CACHE_FILE = ".media-upgrade-hashes.json"
_CACHE_VERSION = 1


@dataclass(slots=True)
class LocalMediaHashCache:
    path: Path
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    _dirty: bool = False

    @classmethod
    def load(cls, album_dir: Path) -> LocalMediaHashCache:
        path = album_dir / _CACHE_FILE
        try:
            payload = json.loads(path.read_text())
            if payload.get("version") != _CACHE_VERSION:
                return cls(path)
            entries = payload.get("items")
            if not isinstance(entries, dict):
                return cls(path)
            return cls(path, entries=entries)
        except FileNotFoundError:
            return cls(path)
        except OSError, json.JSONDecodeError, AttributeError:
            logger.warning("media_upgrade.hash_cache_load_failed", exc_info=True)
            return cls(path)

    def get(self, media_path: Path) -> MediaHash | None:
        entry = self.entries.get(media_path.name)
        try:
            stat = media_path.stat()
        except OSError:
            self.misses += 1
            return None
        if not isinstance(entry, dict) or (
            entry.get("size") != stat.st_size
            or entry.get("mtime_ns") != stat.st_mtime_ns
        ):
            self.misses += 1
            return None
        raw_hashes = entry.get("hashes")
        if (
            not isinstance(raw_hashes, list)
            or not raw_hashes
            or not all(
                isinstance(value, str) and len(value) == 16 for value in raw_hashes
            )
        ):
            self.misses += 1
            return None
        try:
            hashes = [imagehash.hex_to_hash(value) for value in raw_hashes]
        except ValueError:
            self.misses += 1
            return None
        self.hits += 1
        return hashes if media_path.suffix.lower() == ".mp4" else hashes[0]

    def put(self, media_path: Path, media_hash: MediaHash) -> None:
        try:
            stat = media_path.stat()
        except OSError:
            return
        hashes = media_hash if isinstance(media_hash, list) else [media_hash]
        if not hashes:
            return
        self.entries[media_path.name] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "hashes": [str(value) for value in hashes],
        }
        self._dirty = True

    def save(self, valid_names: set[str]) -> None:
        stale = self.entries.keys() - valid_names
        if stale:
            for name in stale:
                del self.entries[name]
            self._dirty = True
        if not self._dirty and self.path.exists():
            return
        payload = {
            "version": _CACHE_VERSION,
            "items": self.entries,
        }
        tmp = self.path.with_suffix(f"{self.path.suffix}.tmp")
        try:
            tmp.write_text(json.dumps(payload, separators=(",", ":")))
            tmp.replace(self.path)
            self._dirty = False
        except OSError:
            logger.warning("media_upgrade.hash_cache_save_failed", exc_info=True)
            tmp.unlink(missing_ok=True)

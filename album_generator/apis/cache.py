"""Caching utilities for API responses."""

import json
import time
from pathlib import Path
from typing import Optional, Any, List, Iterator

CACHE_DIR = Path.home() / ".polarsteps_album_cache"
CACHE_DIR.mkdir(exist_ok=True)


def get_cached(key: str) -> Optional[Any]:
    """Get cached API response."""
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                if time.time() - data.get("timestamp", 0) < 86400:
                    return data.get("value")
        except Exception:
            pass
    return None


def set_cached(key: str, value: Any):
    """Cache API response."""
    cache_file = CACHE_DIR / f"{key}.json"
    try:
        with open(cache_file, "w") as f:
            json.dump({"timestamp": time.time(), "value": value}, f)
    except Exception:
        pass


def _chunks(lst: List[Any], n: int) -> Iterator[List[Any]]:
    """Split list into chunks of size n."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def _load_elevation_cache(cache_file: Path) -> dict[str, Optional[float]]:
    """Load elevation cache from file."""
    if cache_file.exists():
        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ Error loading elevation cache: {e}")
    return {}


def _save_elevation_cache(cache_file: Path, cache: dict[str, Optional[float]]):
    """Save elevation cache to file."""
    try:
        with open(cache_file, "w") as f:
            json.dump(cache, f)
    except IOError as e:
        print(f"⚠️ Error saving elevation cache: {e}")

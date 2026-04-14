"""Detect container resource limits from cgroup v2/v1, with system fallback."""

import os
import shutil
from functools import cache
from pathlib import Path

MiB = 1024 * 1024


def detect_storage_bytes(path: Path) -> int:
    """Filesystem capacity in bytes for the given path.

    On k8s with a PVC mount this returns the PVC size.
    On Docker/local it returns the host disk size.
    Falls back to the first existing ancestor if the path doesn't exist yet.
    """
    while not path.exists():
        path = path.parent
    return shutil.disk_usage(path).total


@cache
def detect_memory_mb() -> int:
    """Container memory limit in MB from cgroup, with system fallback."""
    try:
        raw = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        if raw != "max":
            return int(raw) // MiB
    except ValueError, OSError:
        pass
    # cgroup v1 returns a near-max-int64 sentinel (~9.2e18) when unlimited
    try:
        limit = int(
            Path("/sys/fs/cgroup/memory/memory.limit_in_bytes").read_text().strip()
        )
        if limit < 2**62:
            return limit // MiB
    except ValueError, OSError:
        pass
    return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") // MiB

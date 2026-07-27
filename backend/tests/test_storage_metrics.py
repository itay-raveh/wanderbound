import asyncio
import shutil
from pathlib import Path
from unittest.mock import call, patch

import pytest

from app.logic import storage_metrics


def test_capture_filesystem_storage_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    usage = shutil._ntuple_diskusage(total=50_000, used=12_000, free=38_000)
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: usage)

    with patch("sentry_sdk.metrics.gauge") as gauge:
        storage_metrics.capture_filesystem_storage_metrics(tmp_path)

    assert gauge.call_args_list == [
        call("storage.filesystem.available_bytes", 38_000, unit="byte"),
        call("storage.filesystem.capacity_bytes", 50_000, unit="byte"),
    ]


async def test_storage_metrics_loop_reports_immediately_and_repeats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filesystem_captures: list[Path] = []

    def capture_filesystem(path: Path) -> None:
        filesystem_captures.append(path)

    async def sleep(_seconds: float) -> None:
        if len(filesystem_captures) == 2:
            raise RuntimeError("stop loop")

    monkeypatch.setattr(
        storage_metrics, "capture_filesystem_storage_metrics", capture_filesystem
    )
    monkeypatch.setattr(asyncio, "sleep", sleep)

    with pytest.raises(RuntimeError, match="stop loop"):
        await storage_metrics.storage_metrics_loop(tmp_path)

    assert filesystem_captures == [tmp_path, tmp_path]


async def test_storage_metrics_loop_recovers_after_capture_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = 0

    def capture_filesystem(_path: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("storage unavailable")

    async def sleep(_seconds: float) -> None:
        if attempts == 2:
            raise RuntimeError("stop loop")

    monkeypatch.setattr(
        storage_metrics, "capture_filesystem_storage_metrics", capture_filesystem
    )
    monkeypatch.setattr(asyncio, "sleep", sleep)

    with pytest.raises(RuntimeError, match="stop loop"):
        await storage_metrics.storage_metrics_loop(tmp_path)

    assert attempts == 2

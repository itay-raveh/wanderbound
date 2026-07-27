import asyncio
import shutil
from pathlib import Path

import sentry_sdk
import structlog

_CAPTURE_INTERVAL_SECONDS = 300
logger = structlog.get_logger(__name__)


def sizes_by_album(users_folder: Path) -> tuple[int, dict[tuple[int, str], int]]:
    if not users_folder.exists():
        return 0, {}
    by_album: dict[tuple[int, str], int] = {}
    for user_folder in users_folder.iterdir():
        try:
            uid = int(user_folder.name)
        except ValueError:
            continue
        trips_folder = user_folder / "trip"
        if not trips_folder.is_dir():
            continue
        for album_folder in trips_folder.iterdir():
            if album_folder.is_dir():
                by_album[(uid, album_folder.name)] = sum(
                    file.stat().st_size
                    for file in album_folder.rglob("*")
                    if file.is_file()
                )
    return sum(by_album.values()), by_album


def capture_media_storage_metrics(used_bytes: int, limit_bytes: int) -> None:
    sentry_sdk.metrics.gauge("storage.media.used_bytes", used_bytes, unit="byte")
    sentry_sdk.metrics.gauge("storage.media.limit_bytes", limit_bytes, unit="byte")
    sentry_sdk.metrics.gauge(
        "storage.media.utilization",
        used_bytes / limit_bytes * 100,
        unit="percent",
    )


def capture_filesystem_storage_metrics(data_folder: Path) -> None:
    usage = shutil.disk_usage(data_folder)
    sentry_sdk.metrics.gauge(
        "storage.filesystem.available_bytes", usage.free, unit="byte"
    )
    sentry_sdk.metrics.gauge(
        "storage.filesystem.capacity_bytes", usage.total, unit="byte"
    )


async def storage_metrics_loop(data_folder: Path) -> None:
    while True:
        try:
            capture_filesystem_storage_metrics(data_folder)
        except Exception:
            logger.exception("storage.metrics_capture_failed")
        await asyncio.sleep(_CAPTURE_INTERVAL_SECONDS)

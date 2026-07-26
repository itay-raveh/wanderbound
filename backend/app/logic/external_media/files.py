from __future__ import annotations

import shutil
import uuid
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from app.logic.layout.media import is_video
from app.logic.panorama.storage import panorama_asset_paths

if TYPE_CHECKING:
    from app.models.album_media import PanoramaConfig


class MediaAssetTransition:
    def __init__(self, album_dir: Path, media_name: str) -> None:
        self.album_dir = album_dir
        self.media_name = media_name
        self.workspace = album_dir / ".media-transitions" / uuid.uuid4().hex
        self.staging_dir = self.workspace / "staged"
        self._previous: list[tuple[Path, Path]] = []
        self._activated: list[tuple[Path, Path]] = []

    def _current_assets(self, panorama: PanoramaConfig | None) -> list[Path]:
        target = self.album_dir / self.media_name
        assets = [target]
        if is_video(self.media_name) and target.with_suffix(".jpg").exists():
            assets.append(target.with_suffix(".jpg"))
        assets.extend(panorama_asset_paths(self.album_dir, self.media_name, panorama))
        return assets

    def _replacement_assets(
        self,
        replacement: Path,
        replacement_original: tuple[Path, Path] | None,
    ) -> list[tuple[Path, Path]]:
        target = self.album_dir / self.media_name
        assets = [(replacement, target)]
        replacement_poster = replacement.with_suffix(".jpg")
        if is_video(self.media_name) and replacement_poster.exists():
            assets.append((replacement_poster, target.with_suffix(".jpg")))
        if replacement_original is not None:
            assets.append(replacement_original)
        return assets

    def _backup(self, source: Path) -> None:
        backup = self.workspace / "previous" / source.relative_to(self.album_dir)
        backup.parent.mkdir(parents=True, exist_ok=True)
        source.replace(backup)
        self._previous.append((backup, source))

    def _install(self, staged: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(destination)
        self._activated.append((destination, staged))

    def activate(
        self,
        replacement: Path,
        panorama: PanoramaConfig | None,
        *,
        replacement_original: tuple[Path, Path] | None = None,
    ) -> None:
        try:
            for source in self._current_assets(panorama):
                if source.exists():
                    self._backup(source)
            for staged, destination in self._replacement_assets(
                replacement, replacement_original
            ):
                self._install(staged, destination)
        except BaseException:
            self.rollback()
            raise

    def rollback(self) -> None:
        for active, staged in reversed(self._activated):
            if active.exists():
                staged.parent.mkdir(parents=True, exist_ok=True)
                active.replace(staged)
        self._activated.clear()
        for backup, original in reversed(self._previous):
            if backup.exists():
                original.parent.mkdir(parents=True, exist_ok=True)
                backup.replace(original)
        self._previous.clear()
        self.discard()

    def finish(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

    def discard(self) -> None:
        with suppress(FileNotFoundError):
            shutil.rmtree(self.workspace)

from pathlib import Path

from src.core.logger import get_logger

logger = get_logger(__name__)


class PhotoRegistry:
    """Registry for all photos in the trip, allowing lookup by ID."""

    def __init__(self, trip_dir: Path) -> None:
        self.trip_dir = trip_dir
        self._photo_map: dict[str, Path] = {}
        self._initialized = False

    def scan(self) -> None:
        """Scans the trip directory for all photos and builds the index."""
        logger.info("Building global photo registry from %s...", self.trip_dir)
        self._photo_map.clear()

        count = self._scan_photos()
        count += self._scan_video_frames()

        self._initialized = True
        logger.info("Registry built. Indexed %d photos.", count)

    def _scan_photos(self) -> int:
        count = 0
        # Look for step directories (heuristic: 'photos' subdir)
        for photo_dir in self.trip_dir.rglob("photos"):
            if not photo_dir.is_dir():
                continue

            for file_path in photo_dir.iterdir():
                if (
                    file_path.is_file()
                    and not file_path.name.startswith(".")
                    and file_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
                ):
                    self._photo_map[file_path.name] = file_path
                    count += 1
        return count

    def _scan_video_frames(self) -> int:
        count = 0
        # Scan video frames cache: trip_dir/*/videos/.psagen_frames
        for frames_dir in self.trip_dir.rglob(".psagen_frames"):
            if not frames_dir.is_dir():
                continue
            for file_path in frames_dir.iterdir():
                if (
                    file_path.is_file()
                    and file_path.suffix.lower() in {".jpg", ".jpeg", ".png"}
                    and file_path.name not in self._photo_map
                ):
                    self._photo_map[file_path.name] = file_path
                    count += 1
        return count

    def get_photo_path(self, photo_id: str) -> Path | None:
        """Get absolute path for a photo ID (filename)."""
        if not self._initialized:
            self.scan()
        return self._photo_map.get(photo_id)

from pathlib import Path

from src.core.logger import get_logger

logger = get_logger(__name__)


class PhotoRegistry:
    def __init__(self, trip_dir: Path) -> None:
        self.trip_dir = trip_dir
        self.photo_map: dict[str, Path] = {}
        self.initialized = False

    def scan(self) -> None:
        """Scans the trip directory for all photos and builds the index."""
        logger.info("Building global photo registry from %s...", self.trip_dir)
        self.photo_map.clear()

        # Look for step directories
        # Pattern usually: {slug}_{id}/photos/{file}
        # We can just glob recursively for photos/

        # Find all 'photos' directories
        count = 0
        for photo_dir in self.trip_dir.rglob("photos"):
            if not photo_dir.is_dir():
                continue

            # Check if parent is a step dir (heuristic: has ID)
            # Actually, just scanning all files in 'photos' subdirs is safe enough
            for file_path in photo_dir.iterdir():
                if (
                    file_path.is_file()
                    and not file_path.name.startswith(".")
                    and file_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
                ):
                    self.photo_map[file_path.name] = file_path
                    count += 1

        # Also scan cache frames if needed?
        # trip_dir/*/photos/.cache/frames
        for frame_dir in self.trip_dir.rglob(".cache/frames"):
            if not frame_dir.is_dir():
                continue
            for file_path in frame_dir.iterdir():
                if (
                    file_path.is_file()
                    and file_path.suffix.lower() in {".jpg", ".jpeg", ".png"}
                    and file_path.name not in self.photo_map
                ):
                    self.photo_map[file_path.name] = file_path
                    count += 1

        self.initialized = True
        logger.info("Registry built. Indexed %d photos.", count)

    def get(self, photo_id: str) -> Path | None:
        if not self.initialized:
            self.scan()
        return self.photo_map.get(photo_id)

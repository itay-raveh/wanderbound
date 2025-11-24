"""Photo management for steps with persistence support."""

import json
from pathlib import Path
from typing import Any

from .logger import get_logger
from .models import Photo, Step

logger = get_logger(__name__)

PHOTOS_BY_PAGES_FILE_NAME = "photos_by_pages.txt"
PHOTOS_MAPPING_FILE_NAME = "photos_mapping.json"
COVER_PHOTO_TEXT_IN_FILE = "Cover photo: "


class PhotoManager:
    """Manages photo loading, saving, and organization for steps."""

    def save_photos_config(
        self,
        steps: list[Step],
        steps_with_photos: dict[int, list[Photo]],
        steps_cover_photos: dict[int, Photo | None],
        steps_photo_pages: dict[int, list[list[Photo]]],
        save_path: Path,
    ) -> None:
        """Save photo configuration to files for manual editing.

        Args:
            steps: List of Step objects
            steps_with_photos: Dictionary mapping step IDs to lists of Photo objects
            steps_cover_photos: Dictionary mapping step IDs to cover Photo (or None)
            steps_photo_pages: Dictionary mapping step IDs to lists of photo pages (each page is a list of Photos)
            save_path: Directory where config files should be saved
        """
        export_photos_mapping_json: dict[str, dict[str, Any]] = {}
        export_line_by_line: list[str] = []

        # Create step ID to step mapping
        step_by_id: dict[int, Step] = {step.id: step for step in steps}

        for step_id, photos in steps_with_photos.items():
            step = step_by_id.get(step_id)
            if not step:
                continue

            step_name = step.get_name_for_photos_export()
            export_line_by_line.append(step_name)

            step_photos_mapping: dict[str, dict[str, Any]] = {}
            for photo in photos:
                step_photos_mapping[str(photo.index)] = photo.to_dict()

            export_photos_mapping_json[str(step_id)] = step_photos_mapping

            # Write cover photo
            cover_photo = steps_cover_photos.get(step_id)
            if cover_photo:
                export_line_by_line.append(
                    COVER_PHOTO_TEXT_IN_FILE + str(cover_photo.index)
                )

            # Write photo pages
            photo_pages = steps_photo_pages.get(step_id, [])
            for page in photo_pages:
                photo_indices = [str(photo.index) for photo in page]
                export_line_by_line.append(" ".join(photo_indices))

            export_line_by_line.append("")

        # Save photos mapping JSON
        mapping_path = save_path / PHOTOS_MAPPING_FILE_NAME
        with open(mapping_path, "w", encoding="utf-8") as f:
            json.dump(export_photos_mapping_json, f, indent=4)

        # Save photos by pages text file
        pages_path = save_path / PHOTOS_BY_PAGES_FILE_NAME
        with open(pages_path, "w", encoding="utf-8") as f:
            f.write("\n".join(export_line_by_line))

        logger.info(
            f"Saved photo configuration to {mapping_path} and {pages_path}",
            extra={"success": True},
        )

    def load_photos_config(
        self, steps: list[Step], save_path: Path
    ) -> dict[int, dict[str, Any]] | None:
        """Load photo configuration from files.

        Args:
            steps: List of Step objects
            save_path: Directory where config files are located

        Returns:
            Dictionary mapping step IDs to photo configuration, or None if files don't exist
        """
        mapping_path = save_path / PHOTOS_MAPPING_FILE_NAME
        pages_path = save_path / PHOTOS_BY_PAGES_FILE_NAME

        if not mapping_path.exists() or not pages_path.exists():
            logger.debug("No photo configuration files found, using defaults")
            return None

        try:
            with open(mapping_path, encoding="utf-8") as f:
                photos_mapping = json.load(f)

            with open(pages_path, encoding="utf-8") as f:
                photos_by_pages = f.read().splitlines()

            # Create step name to step mapping
            step_by_name: dict[str, Step] = {}
            for step_obj in steps:
                step_by_name[step_obj.get_name_for_photos_export()] = step_obj

            config: dict[int, dict[str, Any]] = {}

            i = 0
            while i < len(photos_by_pages):
                line = photos_by_pages[i].strip()
                if not line:
                    i += 1
                    continue

                # Find matching step
                matched_step: Step | None = None
                for step_name, step_obj in step_by_name.items():
                    if line == step_name:
                        matched_step = step_obj
                        break

                if matched_step is None:
                    logger.warning(
                        f"Step '{line}' in photos config not found in trip data, skipping"
                    )
                    # Skip to next empty line
                    while i < len(photos_by_pages) and photos_by_pages[i].strip():
                        i += 1
                    continue

                i += 1
                if i >= len(photos_by_pages):
                    break

                # Parse cover photo
                cover_photo_index: int | None = None
                if photos_by_pages[i].startswith(COVER_PHOTO_TEXT_IN_FILE):
                    cover_photo_str = photos_by_pages[i].removeprefix(
                        COVER_PHOTO_TEXT_IN_FILE
                    )
                    try:
                        cover_photo_index = int(cover_photo_str)
                    except ValueError:
                        logger.warning(
                            f"Invalid cover photo index '{cover_photo_str}' for step {matched_step.city}"
                        )
                    i += 1

                # Parse photo pages
                photo_pages: list[list[int]] = []
                while i < len(photos_by_pages) and photos_by_pages[i].strip():
                    page_line = photos_by_pages[i].strip()
                    photo_indices = [int(idx) for idx in page_line.split() if idx]
                    if photo_indices:
                        photo_pages.append(photo_indices)
                    i += 1

                # Reconstruct Photo objects from mapping
                step_photos_mapping = photos_mapping.get(str(matched_step.id), {})
                reconstructed_photos: list[Photo] = []
                for photo_idx_str, photo_data in step_photos_mapping.items():
                    try:
                        photo = Photo.from_dict(photo_data)
                        reconstructed_photos.append(photo)
                    except Exception as e:
                        logger.warning(
                            f"Error reconstructing photo {photo_idx_str} for step {matched_step.city}: {e}"
                        )

                config[matched_step.id] = {
                    "cover_photo_index": cover_photo_index,
                    "photo_pages": photo_pages,
                    "photos": reconstructed_photos,
                }

            return config if config else None

        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Error loading photo configuration: {e}")
            return None

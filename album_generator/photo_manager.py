"""Photo management for steps with persistence support."""

import json
from pathlib import Path

from .logger import get_logger
from .models import Photo, Step
from .settings import get_settings
from .types import PhotoConfigDict, PhotoDataDict, StepPhotoConfigDict

logger = get_logger(__name__)

__all__ = ["save_photos_config", "load_photos_config"]


def save_photos_config(
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
    settings = get_settings()
    export_photos_mapping_json: dict[str, StepPhotoConfigDict] = {}
    export_line_by_line: list[str] = []

    step_by_id: dict[int, Step] = {step.id: step for step in steps}

    for step_id, photos in steps_with_photos.items():
        step = step_by_id.get(step_id)
        if not step:
            continue

        step_name = step.get_name_for_photos_export()
        export_line_by_line.append(step_name)

        step_photos_mapping: dict[str, PhotoDataDict] = {}
        for photo in photos:
            photo_dict = photo.to_dict()
            step_photos_mapping[str(photo.index)] = PhotoDataDict(
                id=photo_dict["id"],
                index=photo_dict["index"],
                path=photo_dict["path"],
                width=photo_dict["width"],
                height=photo_dict["height"],
                aspect_ratio=photo_dict["aspect_ratio"],
            )

        step_config: StepPhotoConfigDict = {"photos": step_photos_mapping}
        export_photos_mapping_json[str(step_id)] = step_config

        cover_photo = steps_cover_photos.get(step_id)
        if cover_photo:
            export_line_by_line.append(settings.file.cover_photo_prefix + str(cover_photo.index))

        photo_pages = steps_photo_pages.get(step_id, [])
        for page in photo_pages:
            photo_indices = [str(photo.index) for photo in page]
            export_line_by_line.append(" ".join(photo_indices))

        export_line_by_line.append("")

    mapping_path = save_path / settings.file.photos_mapping_file
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(export_photos_mapping_json, f, indent=4)

    pages_path = save_path / settings.file.photos_by_pages_file
    with open(pages_path, "w", encoding="utf-8") as f:
        f.write("\n".join(export_line_by_line))

    logger.info(
        f"Saved photo configuration to {mapping_path} and {pages_path}",
        extra={"success": True},
    )


def load_photos_config(steps: list[Step], save_path: Path) -> dict[int, PhotoConfigDict] | None:
    """Load photo configuration from files.

    Args:
        steps: List of Step objects
        save_path: Directory where config files are located

    Returns:
        Dictionary mapping step IDs to photo configuration, or None if files don't exist
    """
    settings = get_settings()
    mapping_path = save_path / settings.file.photos_mapping_file
    pages_path = save_path / settings.file.photos_by_pages_file

    if not mapping_path.exists() or not pages_path.exists():
        logger.debug("No photo configuration files found, using defaults")
        return None

    try:
        with open(mapping_path, encoding="utf-8") as f:
            photos_mapping = json.load(f)

        with open(pages_path, encoding="utf-8") as f:
            photos_by_pages = f.read().splitlines()

        step_by_name: dict[str, Step] = {}
        for step_obj in steps:
            step_by_name[step_obj.get_name_for_photos_export()] = step_obj

        config: dict[int, PhotoConfigDict] = {}

        i = 0
        while i < len(photos_by_pages):
            line = photos_by_pages[i].strip()
            if not line:
                i += 1
                continue

            matched_step: Step | None = None
            for step_name, step_obj in step_by_name.items():
                if line == step_name:
                    matched_step = step_obj
                    break

            if matched_step is None:
                logger.warning(f"Step '{line}' in photos config not found in trip data, skipping")
                # Skip to next empty line
                while i < len(photos_by_pages) and photos_by_pages[i].strip():
                    i += 1
                continue

            i += 1
            if i >= len(photos_by_pages):
                break

            cover_photo_index: int | None = None
            if photos_by_pages[i].startswith(settings.file.cover_photo_prefix):
                cover_photo_str = photos_by_pages[i].removeprefix(settings.file.cover_photo_prefix)
                try:
                    cover_photo_index = int(cover_photo_str)
                except ValueError:
                    logger.warning(
                        f"Invalid cover photo index '{cover_photo_str}' for step '{matched_step.city}'. "
                        f"Expected a number. Skipping cover photo for this step."
                    )
                i += 1

            photo_pages: list[list[int]] = []
            while i < len(photos_by_pages) and photos_by_pages[i].strip():
                page_line = photos_by_pages[i].strip()
                photo_indices = [int(idx) for idx in page_line.split() if idx]
                if photo_indices:
                    photo_pages.append(photo_indices)
                i += 1

                # Reconstruct Photo objects from mapping
                step_config_data = photos_mapping.get(str(matched_step.id), {})
                if not isinstance(step_config_data, dict):
                    logger.warning(
                        f"Invalid photo config data for step '{matched_step.city}', skipping"
                    )
                    continue

                step_photos_mapping = step_config_data.get("photos", {})

                reconstructed_photos: list[Photo] = []
                for photo_idx_str, photo_data in step_photos_mapping.items():
                    try:
                        if isinstance(photo_data, dict):
                            photo = Photo.from_dict(photo_data)
                            reconstructed_photos.append(photo)
                    except Exception as e:
                        logger.warning(
                            f"Error reconstructing photo {photo_idx_str} for step '{matched_step.city}': {e}. "
                            f"Skipping this photo and continuing."
                        )

                photos_dict: dict[str, PhotoDataDict] = {}
                for p in reconstructed_photos:
                    photo_dict = p.to_dict()
                    photos_dict[str(p.index)] = PhotoDataDict(
                        id=photo_dict["id"],
                        index=photo_dict["index"],
                        path=photo_dict["path"],
                        width=photo_dict["width"],
                        height=photo_dict["height"],
                        aspect_ratio=photo_dict["aspect_ratio"],
                    )

                config[matched_step.id] = {
                    "cover_photo_index": cover_photo_index,
                    "photo_pages": photo_pages,
                    "photos": photos_dict,
                }

        return config if config else None

    except FileNotFoundError as e:
        logger.warning(
            f"Photo configuration file not found: {e}. "
            f"Will generate new configuration from photos."
        )
        return None
    except json.JSONDecodeError as e:
        logger.warning(
            f"Invalid JSON in photo configuration file {mapping_path}: {e}. "
            f"Please check the file format. Will generate new configuration."
        )
        return None
    except ValueError as e:
        logger.warning(
            f"Error parsing photo configuration: {e}. "
            f"Will generate new configuration from photos."
        )
        return None

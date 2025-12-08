"""Photo loading and metadata extraction."""

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps

from src.core.logger import get_logger
from src.data.models import Photo
from src.media.similarity import are_similar, compute_image_hash
from src.media.video import extract_best_frame

logger = get_logger(__name__)


@lru_cache(maxsize=512)
def _load_photo_metadata(img_path: Path) -> tuple[int, int, float] | None:
    try:
        with Image.open(img_path) as img:
            img_rotated = ImageOps.exif_transpose(img)
            width, height = img_rotated.size
            aspect_ratio = width / height if height > 0 else 0
            return (width, height, aspect_ratio)
    except (OSError, ValueError, AttributeError, TypeError) as e:
        logger.debug("Error loading image metadata for %s: %s", img_path, e)
        return None


def _load_single_photo(img_path: Path, index: int) -> Photo | None:
    metadata = _load_photo_metadata(img_path)
    if metadata is None:
        return None

    width, height, aspect_ratio = metadata
    return Photo(
        id=img_path.name,
        index=index,
        path=img_path,
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
    )


def load_step_photos(photo_dir: Path) -> list[Photo]:
    if not photo_dir.exists():
        logger.warning("Photo directory does not exist: %s", photo_dir)
        return []

    image_extensions = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}
    image_files = sorted(
        [f for f in photo_dir.iterdir() if f.suffix in image_extensions and f.is_file()]
    )

    photos = []
    seen_hashes = set()

    # Process and hash existing images
    for index, img_path in enumerate(image_files, start=1):
        photo = _load_single_photo(img_path, index)
        if photo:
            photos.append(photo)
            # Compute hash for duplicate detection
            h = compute_image_hash(img_path)
            if h is not None:
                seen_hashes.add(h)

    _process_step_videos(photo_dir, photos, seen_hashes)
    return photos


def _process_step_videos(photo_dir: Path, photos: list[Photo], seen_hashes: set[int]) -> None:
    video_extensions = {".mp4", ".mov", ".avi", ".MP4", ".MOV", ".AVI"}

    # Check both the photos directory and a sibling 'videos' directory
    video_files = []

    # Check in photos dir
    video_files.extend(
        [f for f in photo_dir.iterdir() if f.suffix in video_extensions and f.is_file()]
    )

    # Check in sibling videos dir
    videos_dir = photo_dir.parent / "videos"
    if videos_dir.exists() and videos_dir.is_dir():
        video_files.extend(
            [f for f in videos_dir.iterdir() if f.suffix in video_extensions and f.is_file()]
        )

    video_files = sorted(video_files)

    if not video_files:
        return

    logger.info("Found %d videos in %s", len(video_files), photo_dir.parent.name)

    # Prepare cache directory for frames
    # We'll use a hidden .cache folder inside the photo_dir
    cache_dir = photo_dir / ".cache" / "frames"

    current_index = len(photos) + 1

    for video_path in video_files:
        photo_added = _process_single_video(
            video_path, cache_dir, photos, seen_hashes, current_index
        )
        if photo_added:
            current_index += 1


def _process_single_video(
    video_path: Path,
    cache_dir: Path,
    photos: list[Photo],
    seen_hashes: set[int],
    current_index: int,
) -> bool:
    # Define cache filename: video_name.jpg
    frame_filename = f"{video_path.stem}_frame.jpg"
    frame_path = cache_dir / frame_filename

    # Extract if not cached
    if not frame_path.exists():
        logger.debug("Extracting frame from %s...", video_path.name)
        extracted = extract_best_frame(video_path, frame_path)
        if not extracted:
            logger.warning("Failed to extract frame from %s", video_path.name)
            return False
        logger.debug("Successfully extracted frame to %s", frame_path.name)
    else:
        logger.debug("Using cached frame for %s", video_path.name)

    # Check similarity
    frame_hash = compute_image_hash(frame_path)
    if frame_hash is not None:
        is_duplicate = False
        for existing_hash in seen_hashes:
            if are_similar(
                frame_hash, existing_hash, threshold=10
            ):  # Slightly higher threshold for video frames
                is_duplicate = True
                logger.debug(
                    "Skipping video frame from %s: similar to existing photo.", video_path.name
                )
                break

        if is_duplicate:
            return False

        seen_hashes.add(frame_hash)

    # Load as photo
    photo = _load_single_photo(frame_path, current_index)
    if photo:
        # Override ID to indicate it's from a video? Or just keep filename
        # Keeping filename is fine, maybe useful to know source
        photos.append(photo)
        return True
    return False

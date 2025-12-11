import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def evaluate_frame_quality(frame: np.ndarray[Any, Any]) -> float:
    """Calculate a quality score for the frame based on sharpness and brightness.

    Higher is better.
    """
    try:
        if frame is None or frame.size == 0:
            return -1.0

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 1. Sharpness (Variance of Laplacian) - good for detecting blur
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        # 2. Brightness evaluation
        # We want to avoid very dark or very bright images
        mean_brightness = float(np.mean(gray))

        # Define approximate optimal brightness (middle gray)
        optimal_brightness = 127.5

        # Calculate distance from optimal brightness (0 to 127.5)
        brightness_dist = abs(mean_brightness - optimal_brightness)

        # Penalty factor: drastic penalty for being too close to 0 or 255
        # If brightness is within 60-195 range, penalty is low
        brightness_penalty = 0.0
        if mean_brightness < 40 or mean_brightness > 215:
            brightness_penalty = 500.0  # Heavy penalty for essentially black/white frames
        else:
            brightness_penalty = brightness_dist * 2.0

        # Combine: prefer sharp images, penalize bad exposure
        # Sharpness values can be in range 0-1000+, brightness penalty ~0-200
        return float(sharpness - brightness_penalty)

    except (ValueError, cv2.error):
        return -1.0


def extract_best_frame(
    video_path: Path, output_path: Path, num_candidates: int = 15
) -> Path | None:
    """Extracts the 'best' frame from a video file by sampling candidates and scoring them.

    Samples 'num_candidates' frames evenly distributed from 10% to 90% of video duration.
    """
    if not video_path.exists():
        logger.error("Video file not found: %s", video_path)
        return None

    cap = None
    best_frame = None

    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.error("Could not open video file: %s", video_path)
            return None

        total_frames = _get_total_frames(cap, video_path)
        if total_frames:
            best_frame = _find_best_candidate(cap, total_frames, num_candidates)

    except (OSError, cv2.error) as e:
        logger.exception("Error extracting frame from %s", video_path, exc_info=e)
        return None
    except Exception:
        logger.exception("Unexpected error extracting frame from %s", video_path)
        return None
    finally:
        if cap:
            cap.release()

    if best_frame is not None:
        # Create parent dirs if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), best_frame)
        return output_path

    logger.warning("No valid frames extracted from %s", video_path.name)
    return None


def _get_total_frames(cap: cv2.VideoCapture, video_path: Path) -> int | None:
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames > 0:
        return total_frames

    # Fallback for flows where metadata is missing
    # Try to read the first valid frame
    ret, _ = cap.read()
    if not ret:
        logger.error("Video file seems empty or corrupt: %s", video_path)
        return None

    # Reset and just take the beginning if we can't seek effectively without total frames
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    # Assume ~10 seconds at 30fps
    return 300


def _find_best_candidate(
    cap: cv2.VideoCapture, total_frames: int, num_candidates: int
) -> np.ndarray[Any, Any] | None:
    # Define candidate positions
    # We'll calculate indices from 10% to 90% to avoid fade-ins/outs
    start_ratio = 0.1
    end_ratio = 0.9

    step_size = (total_frames * (end_ratio - start_ratio)) / max(1, num_candidates - 1)
    start_frame = total_frames * start_ratio

    best_score = -float("inf")
    best_frame = None

    for i in range(num_candidates):
        frame_idx = int(start_frame + i * step_size)
        frame_idx = max(0, min(frame_idx, total_frames - 1))

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()

        if not ret:
            continue

        score = evaluate_frame_quality(frame)

        if score > best_score:
            best_score = score
            best_frame = frame.copy()

    return best_frame

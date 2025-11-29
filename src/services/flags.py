"""Country flag API and color extraction."""

import base64
import hashlib
import io
from collections import Counter

from PIL import Image

from src.core.logger import get_logger
from src.core.settings import settings
from src.data.models import FlagResult
from src.services.utils import APIClient
from src.utils.colors import adjust_color_for_contrast, get_color_distance

logger = get_logger(__name__)

_COUNTRY_COLORS: dict[str, str] = {}


def _nudge_color_to_avoid_conflict(color: str, country_code: str) -> str:
    if not color or not color.startswith("#"):
        return color

    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)

    for other_code, other_color in _COUNTRY_COLORS.items():
        if other_code != country_code:
            dist = get_color_distance(color, other_color)
            if dist < settings.color_conflict_threshold:
                hash_val = int(hashlib.md5(country_code.encode()).hexdigest(), 16)

                dominant = max(r, g, b)
                if dominant == r and r > g + 20 and r > b + 20:
                    r = max(0, min(255, r + ((hash_val % 16) - 8)))
                    g = max(0, min(255, g + ((hash_val % 6) - 3)))
                    b = max(0, min(255, b + ((hash_val % 6) - 3)))
                elif dominant == g and g > r + 20 and g > b + 20:
                    g = max(0, min(255, g + ((hash_val % 16) - 8)))
                    r = max(0, min(255, r + ((hash_val % 6) - 3)))
                    b = max(0, min(255, b + ((hash_val % 6) - 3)))
                elif dominant == b and b > r + 20 and b > g + 20:
                    b = max(0, min(255, b + ((hash_val % 16) - 8)))
                    r = max(0, min(255, r + ((hash_val % 6) - 3)))
                    g = max(0, min(255, g + ((hash_val % 6) - 3)))
                else:
                    r = max(0, min(255, r + ((hash_val % 10) - 5)))
                    g = max(0, min(255, g + (((hash_val >> 8) % 10) - 5)))
                    b = max(0, min(255, b + (((hash_val >> 16) % 10) - 5)))

                color = f"#{r:02x}{g:02x}{b:02x}"
                break

    return color


def _load_and_filter_flag_pixels(
    flag_data_uri: str,
) -> list[tuple[int, int, int]] | None:
    """Load flag image and filter pixels by brightness."""
    try:
        base64_data = flag_data_uri.split(",")[1]
        image_bytes = base64.b64decode(base64_data)
        image_obj = Image.open(io.BytesIO(image_bytes))
        image = image_obj.convert("RGB") if image_obj.mode != "RGB" else image_obj

        pixels: list[tuple[int, int, int]] = list(image.getdata())
        filtered_pixels = []
        for r, g, b in pixels:
            brightness = (r + g + b) / 3
            if (
                brightness > settings.brightness_threshold_high
                or brightness < settings.brightness_threshold_low
            ):
                continue
            filtered_pixels.append((r, g, b))
    except (OSError, ValueError, AttributeError) as e:
        logger.debug("Error loading flag image: %s", e)
        return None
    else:
        return filtered_pixels if filtered_pixels else None


def _has_color_conflict(candidate_color: str, country_code: str) -> bool:
    """Check if a candidate color conflicts with existing country colors."""
    country_code_lower = country_code.lower()
    for other_code, other_color in _COUNTRY_COLORS.items():
        if other_code != country_code_lower:
            dist = get_color_distance(candidate_color, other_color)
            if dist < settings.color_conflict_threshold:
                return True
    return False


def _find_best_color_from_candidates(
    color_counts: list[tuple[tuple[int, int, int], int]],
    country_code: str | None,
    *,
    light_mode: bool,
) -> str | None:
    if not color_counts:
        return None

    most_common_count = color_counts[0][1]

    for color_tuple, count in color_counts:
        if count < most_common_count * settings.color_count_min_ratio:
            break

        r, g, b = color_tuple
        candidate_color = f"#{r:02x}{g:02x}{b:02x}"

        if country_code and _has_color_conflict(candidate_color, country_code):
            continue

        color = adjust_color_for_contrast(candidate_color, light_mode=light_mode)
        if country_code:
            _COUNTRY_COLORS[country_code.lower()] = color
        return color

    return None


def extract_prominent_color_from_flag(
    flag_data_uri: str | None,
    country_code: str | None = None,
    *,
    light_mode: bool = False,
) -> str:
    """Extract the most common non-white/black color from a country flag image."""
    default_color = settings.default_accent_color

    if (
        not flag_data_uri
        or not isinstance(flag_data_uri, str)
        or not flag_data_uri.startswith("data:image")
    ):
        if not flag_data_uri or not isinstance(flag_data_uri, str):
            logger.debug("No flag data URI provided, using default accent color")
        else:
            logger.debug("Invalid flag data URI format, using default accent color")
        return default_color

    try:
        filtered_pixels = _load_and_filter_flag_pixels(flag_data_uri)
        color_counts = Counter(filtered_pixels).most_common(5) if filtered_pixels else None

        if not color_counts:
            logger.debug("No suitable pixels or color counts found, using default accent color")
            return default_color

        # Try to find a color without conflicts
        best_color = _find_best_color_from_candidates(
            color_counts, country_code, light_mode=light_mode
        )
        if best_color:
            return best_color

        # Fallback to most common color, nudging if needed to avoid conflicts
        r, g, b = color_counts[0][0]
        color = f"#{r:02x}{g:02x}{b:02x}"

        if country_code:
            color = _nudge_color_to_avoid_conflict(color, country_code.lower())

        color = adjust_color_for_contrast(color, light_mode=light_mode)

        if country_code:
            _COUNTRY_COLORS[country_code.lower()] = color
    except (ValueError, AttributeError, KeyError, TypeError, OSError):
        logger.exception("Error extracting color from flag")
        return default_color
    else:
        return color


async def get_flag_data(
    client: APIClient, country_code: str, step_index: int, *, light_mode: bool
) -> FlagResult:
    """Get country flag image and extracted accent color."""
    if not country_code:
        return FlagResult(step_index=step_index)

    url = settings.flag_cdn_url.format(country_code=country_code.lower())

    try:
        content = await client.get_content(url)
        image_data = base64.b64encode(content).decode("utf-8")
        flag_url = f"data:image/png;base64,{image_data}"

        accent_color = extract_prominent_color_from_flag(
            flag_url, country_code, light_mode=light_mode
        )

        return FlagResult(step_index=step_index, flag_url=flag_url, accent_color=accent_color)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to get flag for %s: %s", country_code, e)
        return FlagResult(step_index=step_index)

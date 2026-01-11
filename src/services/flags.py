"""Country flag API and color extraction."""

import asyncio
import base64
import math
from collections import Counter
from collections.abc import Callable, Iterable
from io import BytesIO

from PIL import Image

from src.core.cache import cache_in_file
from src.core.logger import get_logger
from src.core.settings import settings
from src.data.models import FlagData, Step
from src.services.client import APIClient

logger = get_logger(__name__)

# Threshold for linear RGB conversion in relative luminance calculation
_LINEAR_RGB_THRESHOLD = 0.03928

# Color extraction and adjustment constants
_COLOR_COUNT_MIN_RATIO = 0.3
_LIGHT_MODE_TARGET_BRIGHTNESS = 0.55
_DARK_MODE_TARGET_BRIGHTNESS = 0.45
_MAX_BLEND_FACTOR = 0.25

RGB = tuple[int, int, int]

_FLAGS: dict[str, bytes] = {}
_COLORS: dict[str, RGB | None] = {}


def _color_distance(color1: RGB, color2: RGB) -> float:
    """Calculate the distance between two RGB colors using the 'redmean' approximation.

    This provides a better approximation of human color perception than standard Euclidean distance
    without the overhead of converting to CIELAB color space.
    """
    r1, g1, b1 = color1
    r2, g2, b2 = color2

    rmean = (r1 + r2) / 2
    dr = r1 - r2
    dg = g1 - g2
    db = b1 - b2

    # https://www.compuphase.com/cmetric.htm
    weight_r = 2 + rmean / 256
    weight_g = 4.0
    weight_b = 2 + (255 - rmean) / 256

    distance = math.sqrt(weight_r * dr * dr + weight_g * dg * dg + weight_b * db * db)

    # Normalize to 0-1 range. Max distance (black to white) is approx 764.83
    return distance / 765.0


def _color_brightness(color: RGB) -> float:
    """Calculate relative luminance of a hex color."""
    r = color[0] / 255.0
    g = color[1] / 255.0
    b = color[2] / 255.0

    r = r / 12.92 if r <= _LINEAR_RGB_THRESHOLD else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= _LINEAR_RGB_THRESHOLD else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= _LINEAR_RGB_THRESHOLD else ((b + 0.055) / 1.055) ** 2.4

    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _adjust_color_for_contrast(color: RGB, *, light_mode: bool) -> RGB:
    """Adjust color brightness to ensure contrast against background."""
    brightness = _color_brightness(color)
    r, g, b = color

    if light_mode:
        target_brightness = _LIGHT_MODE_TARGET_BRIGHTNESS
        if brightness < target_brightness:
            blend_factor = (
                (target_brightness - brightness) / (1.0 - brightness) if brightness < 1.0 else 0
            )
            blend_factor = min(_MAX_BLEND_FACTOR, blend_factor)
            r = int(r + (255 - r) * blend_factor)
            g = int(g + (255 - g) * blend_factor)
            b = int(b + (255 - b) * blend_factor)
    else:
        target_brightness = _DARK_MODE_TARGET_BRIGHTNESS
        if brightness > target_brightness:
            blend_factor = (brightness - target_brightness) / brightness if brightness > 0 else 0
            blend_factor = min(_MAX_BLEND_FACTOR, blend_factor)
            r = int(r * (1 - blend_factor))
            g = int(g * (1 - blend_factor))
            b = int(b * (1 - blend_factor))

    return max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))


def _brightness_filter(rgb: RGB) -> bool:
    return 0.1 <= _color_brightness(rgb) <= 0.9


def _get_pixels(flag_data: bytes) -> list[RGB]:
    try:
        # noinspection PyTypeChecker
        pixel_view: Iterable[RGB] = Image.open(BytesIO(flag_data)).convert("RGB").getdata()  # ty:ignore[invalid-assignment]
    except OSError as e:
        logger.debug("Error loading flag image: %s", e)
        return []
    else:
        return list(filter(_brightness_filter, pixel_view))


def _find_best_color_from_candidates(
    color_counts: list[tuple[RGB, int]], *, light_mode: bool
) -> RGB | None:
    min_allowed_count = color_counts[0][1] * _COLOR_COUNT_MIN_RATIO

    for rgb, count in color_counts:
        if count < min_allowed_count:
            return None

        for other in _COLORS.values():
            if other and _color_distance(rgb, other) < 0.1:
                break
        else:
            return _adjust_color_for_contrast(rgb, light_mode=light_mode)

    return None


def _extract_prominent_color(flag_data: bytes, *, light_mode: bool) -> RGB | None:
    pixels = _get_pixels(flag_data)

    if not pixels:
        return None

    color_counts = Counter(pixels).most_common(5)

    # Try to find a color without conflicts
    best_color = _find_best_color_from_candidates(color_counts, light_mode=light_mode)
    if best_color:
        return best_color

    # Fallback to most common color, nudging if needed to avoid conflicts
    return _adjust_color_for_contrast(color_counts[0][0], light_mode=light_mode)


@cache_in_file()
async def _get_flag_uri_and_accent(
    client: APIClient, country_code: str, *, light_mode: bool
) -> tuple[str, str]:
    """Get flag URL and accent color, cached by country code and mode."""
    if country_code not in _FLAGS:
        _FLAGS[country_code] = await client.get_content(
            settings.flag_cdn_url.format(country_code=country_code.lower())
        )

    if country_code not in _COLORS:
        _COLORS[country_code] = _extract_prominent_color(
            _FLAGS[country_code], light_mode=light_mode
        )

    b64_flag_data = base64.b64encode(_FLAGS[country_code]).decode("utf-8")
    flag_url = f"data:image/png;base64,{b64_flag_data}"

    if color := _COLORS[country_code]:
        r, g, b = color
        return flag_url, f"#{r:02x}{g:02x}{b:02x}"

    logger.debug("No suitable pixels or color counts found, using default accent color")
    return flag_url, settings.accent_color


async def fetch_flags(
    client: APIClient,
    steps: list[Step],
    *,
    light_mode: bool = False,
    progress_callback: Callable[[int], None],
) -> list[FlagData | None]:
    """Fetch flags and extract colors for all steps."""

    async def _get_and_update_progress(step: Step) -> FlagData | None:
        flag_url, accent_color = await _get_flag_uri_and_accent(
            client, step.location.country_code, light_mode=light_mode
        )

        progress_callback(1)

        return FlagData(flag_url=flag_url, accent_color=accent_color)

    results = await asyncio.gather(
        *(_get_and_update_progress(step) for step in steps),
        return_exceptions=True,
    )

    flag_results: list[FlagData | None] = []
    for i, res in enumerate(results):
        if isinstance(res, FlagData):
            flag_results.append(res)
        else:
            flag_results.append(None)
            logger.warning("Failed to fetch flag for step %d: %s", i, res)

    logger.debug("Processed %d flags", len(flag_results))
    return flag_results

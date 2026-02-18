from __future__ import annotations

import asyncio
import base64
import math
from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image
from pydantic import BaseModel

from psagen.core.cache import async_cache
from psagen.core.logger import get_logger
from psagen.core.settings import settings

if TYPE_CHECKING:
    from collections.abc import Iterator

    from psagen.core.client import APIClient

logger = get_logger(__name__)

# Threshold for linear RGB conversion in relative luminance calculation
_LINEAR_RGB_THRESHOLD = 0.03928

# Color extraction and adjustment constants
_TARGET_BRIGHTNESS = 0.75
_MAX_BLEND_FACTOR = 0.25

RGB = tuple[int, int, int]

_COLOR_LOCK = asyncio.Lock()
_COLORS: dict[str, RGB] = {}


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


def _adjust_color_for_contrast(color: RGB) -> RGB:
    """Adjust color brightness to ensure contrast against background."""
    brightness = _color_brightness(color)
    r, g, b = color

    if brightness > _TARGET_BRIGHTNESS:
        blend_factor = (brightness - _TARGET_BRIGHTNESS) / brightness if brightness > 0 else 0
        blend_factor = min(_MAX_BLEND_FACTOR, blend_factor)
        r = int(r * (1 - blend_factor))
        g = int(g * (1 - blend_factor))
        b = int(b * (1 - blend_factor))

    return max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))


def _get_histogram(im_data: bytes) -> Iterator[tuple[int, RGB]]:
    try:
        with Image.open(BytesIO(im_data)) as img:
            # noinspection PyTypeChecker
            histogram: list[tuple[int, RGB]] = img.convert("RGB").getcolors()  # pyright: ignore[reportAssignmentType]

        yield from sorted(histogram, key=lambda x: x[0], reverse=True)
    except Exception as e:  # noqa: BLE001
        logger.debug("Error loading flag image: %s", e)
        return


def _find_best_color(flag_data: bytes) -> RGB | None:
    for _, color in _get_histogram(flag_data):
        if 0.1 < _color_brightness(color) < 0.9:
            for other in _COLORS.values():
                if other and _color_distance(color, other) < 0.15:
                    break
            else:
                return _adjust_color_for_contrast(color)

    return None


class Flag(BaseModel):
    flag_url: str
    accent_color: str


@async_cache
async def fetch_flag(client: APIClient, country_code: str) -> Flag:
    flag_data = await client.get(settings.flag_cdn_url.format(country_code=country_code.lower()))

    async with _COLOR_LOCK:
        if country_code not in _COLORS:
            color = await asyncio.to_thread(_find_best_color, flag_data)
            if color is None:
                logger.warning("Could not find color %s", country_code)
                color = (30, 30, 30)
            _COLORS[country_code] = color

    b64_svg = base64.b64encode(flag_data).decode("utf-8")
    r, g, b = _COLORS[country_code]
    return Flag(
        flag_url=f"data:image/svg+xml;base64,{b64_svg}",
        accent_color=f"#{r:02x}{g:02x}{b:02x}",
    )

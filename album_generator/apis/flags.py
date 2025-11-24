"""Country flag API and color extraction."""

import requests
import base64
from typing import Optional
from PIL import Image
import io
from collections import Counter
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000

from .cache import get_cached, set_cached
from ..logger import get_logger
from ..constants import (
    DEFAULT_ACCENT_COLOR,
    BRIGHTNESS_THRESHOLD_HIGH,
    BRIGHTNESS_THRESHOLD_LOW,
    COLOR_COUNT_MIN_RATIO,
    COLOR_CONFLICT_THRESHOLD,
    LIGHT_MODE_TARGET_BRIGHTNESS,
    DARK_MODE_TARGET_BRIGHTNESS,
    MAX_BLEND_FACTOR,
)

logger = get_logger(__name__)

_COUNTRY_COLORS = {}


def get_country_flag_data_uri(country_code: str) -> Optional[str]:
    """Get country flag image as data URI."""
    if not country_code:
        return None

    cache_key = f"flag_{country_code.lower()}"
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, str):
        return cached

    try:
        url = f"https://flagcdn.com/w40/{country_code.lower()}.png"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        if response.status_code == 200:
            image_data = base64.b64encode(response.content).decode("utf-8")
            data_uri = f"data:image/png;base64,{image_data}"
            set_cached(cache_key, data_uri)
            return data_uri
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to get flag for {country_code}: {e}")
    except Exception as e:
        logger.error(f"Error processing flag for {country_code}: {e}", exc_info=True)

    return None


def _color_distance(color1: str, color2: str) -> float:
    """Calculate perceptual color distance using Delta E (CIE 2000).
    Returns normalized distance (0-1 scale, 0 = identical).
    Delta E values > 2.3 are considered perceptually different."""
    if not color1.startswith("#") or not color2.startswith("#"):
        return 1.0

    try:
        # Parse hex colors
        r1 = int(color1[1:3], 16) / 255.0
        g1 = int(color1[3:5], 16) / 255.0
        b1 = int(color1[5:7], 16) / 255.0
        r2 = int(color2[1:3], 16) / 255.0
        g2 = int(color2[3:5], 16) / 255.0
        b2 = int(color2[5:7], 16) / 255.0

        # Convert to Lab color space for perceptual distance
        rgb1 = sRGBColor(r1, g1, b1)
        rgb2 = sRGBColor(r2, g2, b2)
        lab1 = convert_color(rgb1, LabColor)
        lab2 = convert_color(rgb2, LabColor)

        # Calculate Delta E (CIE 2000) - perceptually uniform
        delta_e = delta_e_cie2000(lab1, lab2)

        # Normalize: Delta E > 50 is very different, normalize to 0-1
        # Using 50 as max reasonable difference for normalization
        return min(delta_e / 50.0, 1.0)
    except Exception:
        # Fallback to simple RGB distance if conversion fails
        r1 = int(color1[1:3], 16)
        g1 = int(color1[3:5], 16)
        b1 = int(color1[5:7], 16)
        r2 = int(color2[1:3], 16)
        g2 = int(color2[3:5], 16)
        b2 = int(color2[5:7], 16)
        dist = ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5
        return dist / (255 * (3**0.5))


def _get_color_brightness(color: str) -> float:
    """Calculate relative luminance/brightness of a color (0-1, 0 = black, 1 = white)."""
    if not color or not color.startswith("#"):
        return 0.5

    r = int(color[1:3], 16) / 255.0
    g = int(color[3:5], 16) / 255.0
    b = int(color[5:7], 16) / 255.0

    r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4

    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _adjust_color_for_contrast(color: str, light_mode: bool) -> str:
    """Adjust color brightness to ensure good contrast with text."""
    if not color or not color.startswith("#"):
        return color

    brightness = _get_color_brightness(color)
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)

    if light_mode:
        target_brightness = LIGHT_MODE_TARGET_BRIGHTNESS
        if brightness < target_brightness:
            blend_factor = (
                (target_brightness - brightness) / (1.0 - brightness)
                if brightness < 1.0
                else 0
            )
            blend_factor = min(MAX_BLEND_FACTOR, blend_factor)
            r = int(r + (255 - r) * blend_factor)
            g = int(g + (255 - g) * blend_factor)
            b = int(b + (255 - b) * blend_factor)
    else:
        target_brightness = DARK_MODE_TARGET_BRIGHTNESS
        if brightness > target_brightness:
            blend_factor = (
                (brightness - target_brightness) / brightness if brightness > 0 else 0
            )
            blend_factor = min(MAX_BLEND_FACTOR, blend_factor)
            r = int(r * (1 - blend_factor))
            g = int(g * (1 - blend_factor))
            b = int(b * (1 - blend_factor))

    return (
        f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"
    )


def _nudge_color_to_avoid_conflict(color: str, country_code: str) -> str:
    """Nudge a color to avoid conflicts with other countries."""
    if not color or not color.startswith("#"):
        return color

    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)

    for other_code, other_color in _COUNTRY_COLORS.items():
        if other_code != country_code:
            dist = _color_distance(color, other_color)
            if dist < COLOR_CONFLICT_THRESHOLD:
                import hashlib

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


def extract_prominent_color_from_flag(
    flag_data_uri: Optional[str],
    country_code: Optional[str] = None,
    light_mode: bool = False,
) -> str:
    """Extract the most common non-white/black color from a country flag image."""
    if not flag_data_uri or not isinstance(flag_data_uri, str):
        logger.debug("No flag data URI provided, using default accent color")
        return DEFAULT_ACCENT_COLOR

    try:
        if not flag_data_uri.startswith("data:image"):
            logger.debug("Invalid flag data URI format, using default accent color")
            return DEFAULT_ACCENT_COLOR

        base64_data = flag_data_uri.split(",")[1]
        image_bytes = base64.b64decode(base64_data)
        image = Image.open(io.BytesIO(image_bytes))

        if image.mode != "RGB":
            image = image.convert("RGB")

        pixels = list(image.getdata())

        filtered_pixels = []
        for r, g, b in pixels:
            brightness = (r + g + b) / 3
            if brightness > BRIGHTNESS_THRESHOLD_HIGH or brightness < BRIGHTNESS_THRESHOLD_LOW:
                continue
            filtered_pixels.append((r, g, b))

        if not filtered_pixels:
            logger.debug("No suitable pixels found after filtering, using default accent color")
            return DEFAULT_ACCENT_COLOR

        color_counts = Counter(filtered_pixels).most_common(5)
        if not color_counts:
            logger.debug("No color counts found, using default accent color")
            return DEFAULT_ACCENT_COLOR

        total_pixels = len(filtered_pixels)
        most_common_count = color_counts[0][1]

        for color_tuple, count in color_counts:
            if count < most_common_count * COLOR_COUNT_MIN_RATIO:
                break

            r, g, b = color_tuple
            candidate_color = f"#{r:02x}{g:02x}{b:02x}"

            if country_code:
                has_conflict = False
                for other_code, other_color in _COUNTRY_COLORS.items():
                    if other_code != country_code.lower():
                        dist = _color_distance(candidate_color, other_color)
                        if dist < COLOR_CONFLICT_THRESHOLD:
                            has_conflict = True
                            break

                if not has_conflict:
                    color = _adjust_color_for_contrast(candidate_color, light_mode)
                    _COUNTRY_COLORS[country_code.lower()] = color
                    return color
            else:
                color = _adjust_color_for_contrast(candidate_color, light_mode)
                return color

        r, g, b = color_counts[0][0]
        color = f"#{r:02x}{g:02x}{b:02x}"

        if country_code:
            color = _nudge_color_to_avoid_conflict(color, country_code.lower())

        color = _adjust_color_for_contrast(color, light_mode)

        if country_code:
            _COUNTRY_COLORS[country_code.lower()] = color

        return color

    except Exception as e:
        logger.error(f"Error extracting color from flag: {e}", exc_info=True)
        return DEFAULT_ACCENT_COLOR

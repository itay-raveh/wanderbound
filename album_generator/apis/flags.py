"""Country flag API and color extraction."""

import base64
import io
from collections import Counter

from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000
from colormath.color_objects import LabColor, sRGBColor
from PIL import Image

from ..logger import get_logger
from ..settings import get_settings
from .cache import get_cached, set_cached
from .rate_limit import fetch_content_with_retry

logger = get_logger(__name__)

# Flag CDN rate limit: Conservative rate to avoid overwhelming the CDN
FLAG_API_CALLS_PER_SECOND = 2

_COUNTRY_COLORS: dict[str, str] = {}


def get_country_flag_data_uri(country_code: str) -> str | None:
    """Get country flag image as data URI."""
    if not country_code:
        return None

    cache_key = f"flag_{country_code.lower()}"
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, str):
        return str(cached)

    try:
        settings = get_settings()
        url = settings.flag_cdn_url.format(country_code=country_code.lower())
        content = fetch_content_with_retry(
            url,
            timeout=5,
            calls_per_second=FLAG_API_CALLS_PER_SECOND,
        )
        image_data = base64.b64encode(content).decode("utf-8")
        data_uri = f"data:image/png;base64,{image_data}"
        set_cached(cache_key, data_uri)
        return data_uri
    except Exception as e:
        logger.warning(f"Failed to get flag for {country_code}: {e}")

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
        return float(min(delta_e / 50.0, 1.0))
    except Exception:
        # Fallback to simple RGB distance if conversion fails
        r1 = int(color1[1:3], 16)
        g1 = int(color1[3:5], 16)
        b1 = int(color1[5:7], 16)
        r2 = int(color2[1:3], 16)
        g2 = int(color2[3:5], 16)
        b2 = int(color2[5:7], 16)
        dist = ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5
        return float(dist / (255 * (3**0.5)))


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

    settings = get_settings()
    if light_mode:
        target_brightness = settings.light_mode_target_brightness
        if brightness < target_brightness:
            blend_factor = (
                (target_brightness - brightness) / (1.0 - brightness) if brightness < 1.0 else 0
            )
            blend_factor = min(settings.max_blend_factor, blend_factor)
            r = int(r + (255 - r) * blend_factor)
            g = int(g + (255 - g) * blend_factor)
            b = int(b + (255 - b) * blend_factor)
    else:
        target_brightness = settings.dark_mode_target_brightness
        if brightness > target_brightness:
            blend_factor = (brightness - target_brightness) / brightness if brightness > 0 else 0
            blend_factor = min(settings.max_blend_factor, blend_factor)
            r = int(r * (1 - blend_factor))
            g = int(g * (1 - blend_factor))
            b = int(b * (1 - blend_factor))

    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


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
            settings = get_settings()
            if dist < settings.color_conflict_threshold:
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


def _load_and_filter_flag_pixels(
    flag_data_uri: str,
) -> list[tuple[int, int, int]] | None:
    """Load flag image and filter pixels by brightness.

    Args:
        flag_data_uri: Base64-encoded data URI of the flag image

    Returns:
        List of filtered pixel tuples (r, g, b), or None if loading fails
    """
    try:
        base64_data = flag_data_uri.split(",")[1]
        image_bytes = base64.b64decode(base64_data)
        image_obj = Image.open(io.BytesIO(image_bytes))
        image = image_obj.convert("RGB") if image_obj.mode != "RGB" else image_obj

        pixels: list[tuple[int, int, int]] = list(image.getdata())
        filtered_pixels = []
        settings = get_settings()
        for r, g, b in pixels:
            brightness = (r + g + b) / 3
            if (
                brightness > settings.brightness_threshold_high
                or brightness < settings.brightness_threshold_low
            ):
                continue
            filtered_pixels.append((r, g, b))

        return filtered_pixels if filtered_pixels else None
    except Exception as e:
        logger.debug(f"Error loading flag image: {e}")
        return None


def _has_color_conflict(candidate_color: str, country_code: str) -> bool:
    """Check if a candidate color conflicts with existing country colors.

    Args:
        candidate_color: Hex color code to check
        country_code: ISO country code to exclude from conflict check

    Returns:
        True if color conflicts with another country, False otherwise
    """
    country_code_lower = country_code.lower()
    settings = get_settings()
    for other_code, other_color in _COUNTRY_COLORS.items():
        if other_code != country_code_lower:
            dist = _color_distance(candidate_color, other_color)
            if dist < settings.color_conflict_threshold:
                return True
    return False


def _find_best_color_from_candidates(
    color_counts: list[tuple[tuple[int, int, int], int]],
    country_code: str | None,
    light_mode: bool,
) -> str | None:
    """Find the best color from candidate color counts, avoiding conflicts if country_code provided.

    Args:
        color_counts: List of (color_tuple, count) tuples from Counter.most_common()
        country_code: Optional ISO country code for conflict detection
        light_mode: If True, adjust color for light mode contrast

    Returns:
        Hex color code if a suitable color is found, None otherwise
    """
    if not color_counts:
        return None

    most_common_count = color_counts[0][1]
    settings = get_settings()

    for color_tuple, count in color_counts:
        if count < most_common_count * settings.color_count_min_ratio:
            break

        r, g, b = color_tuple
        candidate_color = f"#{r:02x}{g:02x}{b:02x}"

        if country_code and _has_color_conflict(candidate_color, country_code):
            continue

        color = _adjust_color_for_contrast(candidate_color, light_mode)
        if country_code:
            _COUNTRY_COLORS[country_code.lower()] = color
        return color

    return None


def extract_prominent_color_from_flag(
    flag_data_uri: str | None,
    country_code: str | None = None,
    light_mode: bool = False,
) -> str:
    """Extract the most common non-white/black color from a country flag image.

    Args:
        flag_data_uri: Base64-encoded data URI of the flag image, or None
        country_code: ISO country code for conflict detection with other countries
        light_mode: If True, adjust color for light mode contrast; if False, for dark mode

    Returns:
        Hex color code (e.g., "#ff0000") or default accent color if extraction fails
    """
    settings = get_settings()
    if not flag_data_uri or not isinstance(flag_data_uri, str):
        logger.debug("No flag data URI provided, using default accent color")
        return settings.default_accent_color

    if not flag_data_uri.startswith("data:image"):
        logger.debug("Invalid flag data URI format, using default accent color")
        return settings.default_accent_color

    try:
        filtered_pixels = _load_and_filter_flag_pixels(flag_data_uri)
        if not filtered_pixels:
            logger.debug("No suitable pixels found after filtering, using default accent color")
            return settings.default_accent_color

        color_counts = Counter(filtered_pixels).most_common(5)
        if not color_counts:
            logger.debug("No color counts found, using default accent color")
            return settings.default_accent_color

        # Try to find a color without conflicts
        best_color = _find_best_color_from_candidates(color_counts, country_code, light_mode)
        if best_color:
            return best_color

        # Fallback to most common color, nudging if needed to avoid conflicts
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
        settings = get_settings()
        return settings.default_accent_color

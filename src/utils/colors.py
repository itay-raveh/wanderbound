"""Color manipulation and analysis utilities."""

from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000
from colormath.color_objects import LabColor, sRGBColor

from src.core.settings import settings

# Threshold for linear RGB conversion in relative luminance calculation
_LINEAR_RGB_THRESHOLD = 0.03928


def get_color_distance(color1: str, color2: str) -> float:
    """Calculate perceptual color distance using Delta E (CIE 2000)."""
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
    except (ValueError, AttributeError, TypeError):
        # Fallback to simple RGB distance if conversion fails
        r1 = int(color1[1:3], 16)
        g1 = int(color1[3:5], 16)
        b1 = int(color1[5:7], 16)
        r2 = int(color2[1:3], 16)
        g2 = int(color2[3:5], 16)
        b2 = int(color2[5:7], 16)
        dist = ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5
        return float(dist / (255 * (3**0.5)))


def get_color_brightness(color: str) -> float:
    """Calculate relative luminance of a hex color."""
    if not color or not color.startswith("#"):
        return 0.5

    r = int(color[1:3], 16) / 255.0
    g = int(color[3:5], 16) / 255.0
    b = int(color[5:7], 16) / 255.0

    r = r / 12.92 if r <= _LINEAR_RGB_THRESHOLD else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= _LINEAR_RGB_THRESHOLD else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= _LINEAR_RGB_THRESHOLD else ((b + 0.055) / 1.055) ** 2.4

    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def adjust_color_for_contrast(color: str, *, light_mode: bool) -> str:
    """Adjust color brightness to ensure contrast against background."""
    if not color or not color.startswith("#"):
        return color

    brightness = get_color_brightness(color)
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)

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

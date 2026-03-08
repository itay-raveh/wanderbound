import colorsys
import itertools
import math
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, StringConstraints, TypeAdapter

if TYPE_CHECKING:
    from collections.abc import Container

CountryCode = Annotated[str, StringConstraints(to_lower=True, pattern="[a-zA-Z]{2}|00")]

HexColor = Annotated[str, StringConstraints(to_lower=True, pattern="#[0-9a-fA-F]{6}")]


class CountryColors(BaseModel):
    code: CountryCode
    colors: list[HexColor]


_COUNTRIES = TypeAdapter(list[CountryColors]).validate_json(
    (Path(__file__).parent / "country_colors.json").read_bytes()
)


def _hex_to_rgb(hex_color: HexColor) -> tuple[int, int, int]:
    """Convert a hex string to an (R, G, B) tuple."""
    hex_color = hex_color.lstrip("#")
    # noinspection PyTypeChecker
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))  # pyright: ignore[reportReturnType]


def _rgb_to_hex(r: float, g: float, b: float) -> HexColor:
    """Convert (R, G, B) to a hex string."""
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def _color_distance(hex1: HexColor, hex2: HexColor) -> float:
    """Calculates the 'Redmean' color distance."""
    r1, g1, b1 = _hex_to_rgb(hex1)
    r2, g2, b2 = _hex_to_rgb(hex2)

    r_mean = (r1 + r2) / 2
    r_diff = r1 - r2
    g_diff = g1 - g2
    b_diff = b1 - b2

    # Redmean formula
    return math.sqrt(
        (((512 + r_mean) * r_diff * r_diff) / 256)
        + 4 * g_diff * g_diff
        + (((767 - r_mean) * b_diff * b_diff) / 256)
    )


def _darken_color(hex_color: HexColor, factor: float = 0.7) -> HexColor:
    r, g, b = _hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)

    # Darken the lightness (preventing it from going below 0)
    l = max(0.0, l * factor)

    # Convert back to RGB
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return _rgb_to_hex(r * 255, g * 255, b * 255)


def _score_combo(combo: tuple[HexColor, ...]) -> float:
    return min(
        (_color_distance(c1, c2) for c1, c2 in itertools.combinations(combo, 2)),
        default=math.inf,
    )


def build_country_colors(
    codes: Container[str], threshold: float = 150.0
) -> dict[CountryCode, HexColor]:
    countries = [country for country in _COUNTRIES if country.code in codes]
    if not countries:
        return {}

    # Find the combination with the maximum minimum-distance between colors
    best_combo = list(max(itertools.product(*(c.colors for c in countries)), key=_score_combo))

    # Darken the conflicting colors
    for i, j in itertools.combinations(range(len(best_combo)), 2):
        if _color_distance(best_combo[i], best_combo[j]) < threshold:
            best_combo[j] = _darken_color(best_combo[j])

    return {country.code: best_combo[i] for i, country in enumerate(countries)}

from collections.abc import Container, Iterable
from pathlib import Path

from coloraide import Color
from pydantic import BaseModel, TypeAdapter

from app.models.polarsteps import CountryCode, HexColor


class CountryColors(BaseModel):
    code: CountryCode
    colors: list[HexColor]


# Bonus (Delta-E units) given to the primary flag color over the last
# candidate.  Keeps each country's most recognizable color unless an
# alternative is substantially better at avoiding collisions.
_PRIMARY_BONUS = 40.0

_COUNTRIES = TypeAdapter(list[CountryColors]).validate_json(
    (Path(__file__).parent / "country_colors.json").read_bytes()
)


def _color_dist(hex1: HexColor, hex2: HexColor) -> float:
    return Color(hex1).delta_e(Color(hex2), method="76")


def _min_distance(color: HexColor, assigned: Iterable[HexColor]) -> float:
    return min((_color_dist(color, a) for a in assigned), default=float("inf"))


def build_country_colors(
    codes: Container[str],
) -> dict[CountryCode, HexColor]:
    countries = [country for country in _COUNTRIES if country.code in codes]
    if not countries:
        return {}

    # Most constrained first: countries with fewer candidates pick first.
    countries.sort(key=lambda c: len(c.colors))

    assigned: dict[CountryCode, HexColor] = {}
    assigned_colors: list[HexColor] = []

    for country in countries:
        # Score each candidate by its distance from assigned colors,
        # with a bonus for earlier (more representative) candidates.
        # The primary color (index 0) gets a full bonus, decaying for
        # later ones. This means the primary wins unless a later
        # candidate is substantially farther from collisions.
        n = len(country.colors)
        idx = {c: i for i, c in enumerate(country.colors)}
        best = max(
            country.colors,
            key=lambda c: (
                _min_distance(c, assigned_colors)
                + _PRIMARY_BONUS * (n - 1 - idx[c]) / max(n - 1, 1)
            ),
        )
        assigned[country.code] = best
        assigned_colors.append(best)

    return assigned

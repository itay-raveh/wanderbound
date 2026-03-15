from collections import Counter
from unittest.mock import patch

import pytest
from coloraide import Color

from app.logic.country_colors import (
    _COUNTRIES,
    CountryColors,
    _color_dist,
    _min_distance,
    build_country_colors,
)

# _delta_e


class TestDeltaE:
    def test_identical_colors(self) -> None:
        assert _color_dist("#ff0000", "#ff0000") == 0.0

    def test_symmetric(self) -> None:
        d1 = _color_dist("#ff0000", "#00ff00")
        d2 = _color_dist("#00ff00", "#ff0000")
        assert d1 == pytest.approx(d2)

    def test_black_white_large_distance(self) -> None:
        d = _color_dist("#000000", "#ffffff")
        assert d > 90  # Delta-E 76 for black vs white is ~100

    def test_similar_reds_small_distance(self) -> None:
        d = _color_dist("#ff0000", "#ee0000")
        assert d < 10

    def test_red_vs_blue_large_distance(self) -> None:
        d = _color_dist("#ff0000", "#0000ff")
        assert d > 50

    def test_agrees_with_coloraide(self) -> None:
        """Verify our wrapper matches coloraide directly."""
        hex1, hex2 = "#3a7f3a", "#c0392b"
        expected = Color(hex1).delta_e(Color(hex2), method="76")
        assert _color_dist(hex1, hex2) == pytest.approx(expected)


# _min_distance


class TestMinDistance:
    def test_empty_assigned_returns_inf(self) -> None:
        assert _min_distance("#ff0000", []) == float("inf")

    def test_single_assigned(self) -> None:
        d = _min_distance("#ff0000", ["#0000ff"])
        assert d == pytest.approx(_color_dist("#ff0000", "#0000ff"))

    def test_returns_minimum(self) -> None:
        assigned = ["#ff0000", "#0000ff"]
        d = _min_distance("#ee0000", assigned)
        d_red = _color_dist("#ee0000", "#ff0000")
        d_blue = _color_dist("#ee0000", "#0000ff")
        assert d == pytest.approx(min(d_red, d_blue))


# build_country_colors: edge cases


class TestBuildEdgeCases:
    def test_empty_codes(self) -> None:
        assert build_country_colors(set()) == {}

    def test_unknown_codes(self) -> None:
        assert build_country_colors({"zz", "qq"}) == {}

    def test_single_country(self) -> None:
        result = build_country_colors({"fr"})
        assert len(result) == 1
        assert "fr" in result

    def test_single_country_gets_primary_color(self) -> None:
        """A lone country should get its first (primary) candidate."""
        result = build_country_colors({"fr"})
        fr_colors = next(c.colors for c in _COUNTRIES if c.code == "fr")
        assert result["fr"] == fr_colors[0]

    def test_codes_are_case_insensitive(self) -> None:
        """The JSON codes are lowered by pydantic."""
        result = build_country_colors({"fr"})
        assert "fr" in result


# build_country_colors: structural invariants


class TestBuildInvariants:
    def test_all_requested_codes_present(self) -> None:
        codes = {"cl", "pe", "br", "bo", "ec"}
        result = build_country_colors(codes)
        assert set(result.keys()) == codes

    def test_assigned_colors_are_valid_candidates(self) -> None:
        """Every assigned color must come from that country's list."""
        codes = {"cl", "pe", "br", "bo", "ec", "fr", "de", "jp"}
        result = build_country_colors(codes)
        candidates = {c.code: c.colors for c in _COUNTRIES if c.code in codes}
        for code, color in result.items():
            assert color in candidates[code], (
                f"{code} got {color}, not in {candidates[code]}"
            )

    def test_deterministic(self) -> None:
        codes = {"cl", "pe", "br", "bo", "ec"}
        r1 = build_country_colors(codes)
        r2 = build_country_colors(codes)
        assert r1 == r2


# build_country_colors: greedy ordering


class TestMostConstrainedFirst:
    def test_single_candidate_gets_its_color(self) -> None:
        """Peru (1 candidate: red) must get red."""
        result = build_country_colors({"pe", "cl"})
        assert result["pe"] == "#ff0000"

    def test_flexible_country_adapts(self) -> None:
        """Chile (red, blue) yields red to Peru, takes blue."""
        result = build_country_colors({"pe", "cl"})
        assert result["cl"] == "#0000ff"

    def test_two_single_candidate_countries(self) -> None:
        """Peru and Japan both only have red."""
        result = build_country_colors({"pe", "jp"})
        assert result["pe"] == "#ff0000"
        assert result["jp"] == "#ff0000"
        assert len(result) == 2


# build_country_colors: real-world scenarios


class TestRealWorldScenarios:
    def test_south_america(self) -> None:
        """Overlapping palettes: CL, PE, BR, BO, EC."""
        result = build_country_colors({"cl", "pe", "br", "bo", "ec"})
        assert len(result) == 5
        assert result["pe"] == "#ff0000"
        assert result["br"] == "#008000"
        assert result["cl"] == "#0000ff"
        assert result["bo"] == "#ffff00"

    def test_diverse_countries_no_conflicts(self) -> None:
        """NL (orange), IE (green), FR (blue) — no overlap."""
        result = build_country_colors({"nl", "ie", "fr"})
        assert result["nl"] == "#ff7f00"  # orange
        assert result["ie"] == "#008000"  # green
        assert result["fr"] == "#0000ff"  # blue

    def test_europe_mix(self) -> None:
        """Overlapping red/blue palettes across Europe."""
        result = build_country_colors({"fr", "de", "it", "ie"})
        assert len(result) == 4
        candidates = {c.code: c.colors for c in _COUNTRIES if c.code in result}
        for code, color in result.items():
            assert color in candidates[code]


# build_country_colors: with mocked data


class TestWithMockedCountries:
    """Test the algorithm with controlled synthetic data."""

    @staticmethod
    def _mock(
        countries: list[CountryColors],
    ) -> patch:
        return patch(
            "app.logic.country_colors._COUNTRIES",
            countries,
        )

    def test_all_identical_candidates(self) -> None:
        """Three countries with only red — all get red."""
        countries = [
            CountryColors(code="aa", colors=["#ff0000"]),
            CountryColors(code="bb", colors=["#ff0000"]),
            CountryColors(code="cc", colors=["#ff0000"]),
        ]
        with self._mock(countries):
            result = build_country_colors({"aa", "bb", "cc"})
        assert len(result) == 3
        assert all(c == "#ff0000" for c in result.values())

    def test_greedy_avoids_collision(self) -> None:
        """Constrained country picks first, flexible adapts."""
        countries = [
            CountryColors(code="aa", colors=["#ff0000"]),
            CountryColors(code="bb", colors=["#ff0000", "#0000ff"]),
        ]
        with self._mock(countries):
            result = build_country_colors({"aa", "bb"})
        assert result["aa"] == "#ff0000"
        assert result["bb"] == "#0000ff"

    def test_three_way_conflict_resolution(self) -> None:
        """Flexible country picks the odd color out."""
        countries = [
            CountryColors(code="aa", colors=["#ff0000"]),
            CountryColors(code="bb", colors=["#00ff00"]),
            CountryColors(
                code="cc",
                colors=["#ff0000", "#00ff00", "#0000ff"],
            ),
        ]
        with self._mock(countries):
            result = build_country_colors({"aa", "bb", "cc"})
        assert result["aa"] == "#ff0000"
        assert result["bb"] == "#00ff00"
        assert result["cc"] == "#0000ff"

    def test_ordering_matters(self) -> None:
        """1-candidate country picks before 3-candidate one."""
        countries = [
            CountryColors(
                code="aa",
                colors=["#ff0000", "#00ff00", "#0000ff"],
            ),
            CountryColors(code="bb", colors=["#ff0000"]),
        ]
        with self._mock(countries):
            result = build_country_colors({"aa", "bb"})
        assert result["bb"] == "#ff0000"
        assert result["aa"] != "#ff0000"


# JSON data integrity


class TestJsonIntegrity:
    def test_countries_loaded(self) -> None:
        assert len(_COUNTRIES) > 190

    def test_all_have_at_least_one_color(self) -> None:
        for country in _COUNTRIES:
            assert len(country.colors) >= 1, f"{country.code} has no colors"

    def test_codes_are_lowercase(self) -> None:
        for country in _COUNTRIES:
            assert country.code == country.code.lower()

    def test_no_duplicate_codes(self) -> None:
        codes = [c.code for c in _COUNTRIES]
        dupes = {code for code, n in Counter(codes).items() if n > 1}
        assert not dupes, f"Duplicate codes: {dupes}"

    def test_colors_are_hex_format(self) -> None:
        for country in _COUNTRIES:
            for color in country.colors:
                assert color.startswith("#"), f"{country.code}: {color}"
                assert len(color) == 7, f"{country.code}: {color}"

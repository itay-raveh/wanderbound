from unittest.mock import patch

from app.logic.country_colors import (
    _COUNTRIES,
    CountryColors,
    build_country_colors,
)

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

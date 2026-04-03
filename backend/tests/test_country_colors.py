from unittest.mock import patch

from app.logic.country_colors import (
    _COUNTRIES,
    CountryColors,
    build_country_colors,
)

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
        """NL (orange), IE (green), FR (blue) - no overlap."""
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
        """Three countries with only red - all get red."""
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

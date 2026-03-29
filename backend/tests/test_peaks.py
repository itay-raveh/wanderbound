"""Tests for app.logic.spatial.peaks."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.logic.spatial.peaks import (
    PEAK_MAX_DEVIATION,
    PEAK_MIN_PROMINENCE,
    OverpassResponse,
    PeakTags,
    _local_peaks,
    _parse_ele,
    correct_peaks,
)


@dataclass
class _Loc:
    lat: float
    lon: float


def _overpass_json(peaks: list[tuple[float, str]]) -> bytes:
    elements = [
        {"type": "node", "lat": 0, "lon": 0, "tags": {"ele": str(e), "name": n}}
        for e, n in peaks
    ]
    return json.dumps({"elements": elements}).encode()


@contextmanager
def _mock_overpass(peaks: list[tuple[float, str]]) -> Iterator[None]:
    mock_response = MagicMock(status_code=200)
    mock_response.content = _overpass_json(peaks)
    with patch("app.logic.spatial.peaks._client") as mock_client:
        mock_client.return_value.post = AsyncMock(return_value=mock_response)
        yield


class TestParseEle:
    def test_int(self) -> None:
        assert _parse_ele(5327) == 5327.0

    def test_float(self) -> None:
        assert _parse_ele(1234.5) == 1234.5

    def test_plain_string(self) -> None:
        assert _parse_ele("5327") == 5327.0

    def test_string_with_m_suffix(self) -> None:
        assert _parse_ele("5327 m") == 5327.0

    def test_string_with_m_no_space(self) -> None:
        assert _parse_ele("5327m") == 5327.0

    def test_comma_decimal(self) -> None:
        assert _parse_ele("1234,5") == 1234.5

    def test_semicolon_takes_first(self) -> None:
        assert _parse_ele("5327;5300") == 5327.0

    def test_whitespace(self) -> None:
        assert _parse_ele("  5327  ") == 5327.0

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="not a number"):
            _parse_ele("not a number")


class TestOverpassModels:
    def test_peak_tags_from_string(self) -> None:
        tags = PeakTags.model_validate({"ele": "5327 m"})
        assert tags.ele == 5327.0

    def test_peak_tags_from_float(self) -> None:
        tags = PeakTags.model_validate({"ele": 1234.5})
        assert tags.ele == 1234.5

    def test_overpass_response(self) -> None:
        data = {
            "elements": [
                {"tags": {"ele": "5327"}},
                {"tags": {"ele": "4500"}},
            ]
        }
        resp = OverpassResponse.model_validate(data)
        assert len(resp.elements) == 2
        assert resp.elements[0].tags.ele == 5327.0

    def test_overpass_response_empty(self) -> None:
        resp = OverpassResponse.model_validate({"elements": []})
        assert resp.elements == []


class TestLocalPeaks:
    def test_summit_between_valleys(self) -> None:
        # city -> base -> summit -> city
        elevs = [500, 4000, 5200, 500]
        assert list(_local_peaks(elevs)) == [2]

    def test_flat_trip(self) -> None:
        elevs = [50, 60, 45, 55]
        assert list(_local_peaks(elevs)) == []

    def test_high_plateau_no_prominence(self) -> None:
        elevs = [3000, 3100, 3050, 3000]
        assert list(_local_peaks(elevs)) == []

    def test_multiple_peaks(self) -> None:
        elevs = [500, 4500, 1000, 5000, 500]
        assert list(_local_peaks(elevs)) == [1, 3]

    def test_single_high_step(self) -> None:
        # Single step: left=0, right=0
        elevs = [5000]
        assert list(_local_peaks(elevs)) == [0]

    def test_single_low_step(self) -> None:
        elevs = [100]
        assert list(_local_peaks(elevs)) == []

    def test_prominence_exactly_at_threshold(self) -> None:
        # Step at exactly PEAK_MIN_PROMINENCE above both neighbors
        base = 1000
        elevs = [base, base + PEAK_MIN_PROMINENCE, base]
        assert list(_local_peaks(elevs)) == [1]

    def test_prominence_just_below_threshold(self) -> None:
        base = 1000
        elevs = [base, base + PEAK_MIN_PROMINENCE - 1, base]
        assert list(_local_peaks(elevs)) == []

    def test_base_camp_not_detected(self) -> None:
        # base camp is high but not a local max (summit is higher)
        elevs = [500, 4000, 5200, 500]
        peaks = list(_local_peaks(elevs))
        assert 1 not in peaks  # base camp at index 1

    def test_edge_peak_first(self) -> None:
        elevs = [3000, 500, 600]
        assert list(_local_peaks(elevs)) == [0]

    def test_edge_peak_last(self) -> None:
        elevs = [500, 600, 3000]
        assert list(_local_peaks(elevs)) == [2]

    def test_empty_list(self) -> None:
        assert list(_local_peaks([])) == []


class TestCorrectPeaks:
    async def test_no_peaks_returns_original(self) -> None:
        locs = [_Loc(0, 0), _Loc(0, 1), _Loc(0, 2)]
        elevs = [100.0, 110.0, 105.0]
        result = await correct_peaks(locs, elevs)
        assert list(result) == elevs

    async def test_corrects_summit(self) -> None:
        locs = [_Loc(0, 0), _Loc(-16.19, -68.26), _Loc(0, 0)]
        elevs = [500.0, 5236.0, 500.0]

        with _mock_overpass([(5327, "Pico Austria")]):
            result = await correct_peaks(locs, elevs)

        assert result[0] == 500.0  # unchanged
        assert result[1] == 5327.0  # corrected
        assert result[2] == 500.0  # unchanged

    async def test_does_not_lower_elevation(self) -> None:
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, 5400.0, 500.0]

        with _mock_overpass([(5327, "Pico Austria")]):
            result = await correct_peaks(locs, elevs)

        assert result[1] == 5400.0  # unchanged - OSM peak is lower

    async def test_deviation_too_large(self) -> None:
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        dem_val = 3000.0
        osm_val = dem_val * (1 + PEAK_MAX_DEVIATION + 0.01)  # just over 10%
        elevs = [500.0, dem_val, 500.0]

        with _mock_overpass([(osm_val, "Far Peak")]):
            result = await correct_peaks(locs, elevs)

        assert result[1] == dem_val  # unchanged

    async def test_deviation_exactly_at_threshold(self) -> None:
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        dem_val = 5000.0
        osm_val = dem_val * (1 + PEAK_MAX_DEVIATION)  # exactly 10%
        elevs = [500.0, dem_val, 500.0]

        with _mock_overpass([(osm_val, "Boundary Peak")]):
            result = await correct_peaks(locs, elevs)

        assert result[1] == osm_val  # corrected

    async def test_picks_closest_in_elevation(self) -> None:
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, 5236.0, 500.0]

        with _mock_overpass(
            [
                (6088, "Huayna Potosi"),
                (5327, "Pico Austria"),
                (5648, "Condoriri"),
            ]
        ):
            result = await correct_peaks(locs, elevs)

        assert result[1] == 5327.0  # closest to 5236

    async def test_overpass_failure_returns_original(self) -> None:
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, 5236.0, 500.0]

        with patch("app.logic.spatial.peaks._client") as mock_client:
            mock_client.return_value.post = AsyncMock(
                side_effect=httpx.HTTPError("timeout")
            )
            result = await correct_peaks(locs, elevs)

        assert list(result) == elevs

    async def test_overpass_non_200_returns_original(self) -> None:
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, 5236.0, 500.0]

        mock_response = MagicMock(status_code=429)
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429", request=MagicMock(), response=mock_response
        )

        with patch("app.logic.spatial.peaks._client") as mock_client:
            mock_client.return_value.post = AsyncMock(return_value=mock_response)
            result = await correct_peaks(locs, elevs)

        assert list(result) == elevs

    async def test_empty_overpass_response(self) -> None:
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, 5236.0, 500.0]

        with _mock_overpass([]):
            result = await correct_peaks(locs, elevs)

        assert list(result) == elevs

    async def test_multiple_local_peaks_corrected(self) -> None:
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, 4500.0, 1000.0, 5000.0, 500.0]

        with _mock_overpass([(4600, "Peak A"), (5100, "Peak B")]):
            result = await correct_peaks(locs, elevs)

        assert result[1] == 4600.0  # closest to 4500
        assert result[3] == 5100.0  # closest to 5000
        assert result[0] == 500.0  # unchanged
        assert result[2] == 1000.0  # unchanged

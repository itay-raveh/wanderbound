"""Tests for elevation fetching and OSM peak correction.

Covers:
  - elevation.py: Open-Meteo DEM fetching, batching, SRTM model selection,
    weighted rate limiter integration
  - peaks.py: OSM ele parsing, local peak detection, peak correction logic,
    Overpass failure handling, deviation threshold
"""

import json
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
from app.services.open_meteo import OPEN_METEO_MAX_PER_REQUEST, elevations
from tests.conftest import collect_async

# Helpers


@dataclass
class _Loc:
    lat: float
    lon: float


def _overpass_json(peaks: list[tuple[float, str]]) -> bytes:
    """Build a minimal Overpass JSON response from (ele, name) pairs."""
    elements = [
        {"type": "node", "lat": 0, "lon": 0, "tags": {"ele": str(e), "name": n}}
        for e, n in peaks
    ]

    return json.dumps({"elements": elements}).encode()


# _parse_ele


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


# Pydantic models


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


# _local_peaks


class TestLocalPeaks:
    def test_summit_between_valleys(self) -> None:
        # city → base → summit → city
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


# correct_peaks


class TestCorrectPeaks:
    @pytest.mark.anyio
    async def test_no_peaks_returns_original(self) -> None:
        """Flat trip — no local peaks, no Overpass call."""
        locs = [_Loc(0, 0), _Loc(0, 1), _Loc(0, 2)]
        elevs = [100.0, 110.0, 105.0]
        result = await correct_peaks(locs, elevs)
        assert list(result) == elevs

    @pytest.mark.anyio
    async def test_corrects_summit(self) -> None:
        """OSM peak higher than DEM within deviation threshold → corrected."""
        locs = [_Loc(0, 0), _Loc(-16.19, -68.26), _Loc(0, 0)]
        elevs = [500.0, 5236.0, 500.0]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = _overpass_json([(5327, "Pico Austria")])

        with patch("app.logic.spatial.peaks._client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            result = await correct_peaks(locs, elevs)

        assert result[0] == 500.0  # unchanged
        assert result[1] == 5327.0  # corrected
        assert result[2] == 500.0  # unchanged

    @pytest.mark.anyio
    async def test_does_not_lower_elevation(self) -> None:
        """OSM peak lower than DEM → keep DEM value."""
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, 5400.0, 500.0]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = _overpass_json([(5327, "Pico Austria")])

        with patch("app.logic.spatial.peaks._client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            result = await correct_peaks(locs, elevs)

        assert result[1] == 5400.0  # unchanged — OSM peak is lower

    @pytest.mark.anyio
    async def test_deviation_too_large(self) -> None:
        """OSM peak far above DEM (>10%) → skip correction."""
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        dem_val = 3000.0
        osm_val = dem_val * (1 + PEAK_MAX_DEVIATION + 0.01)  # just over 10%
        elevs = [500.0, dem_val, 500.0]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = _overpass_json([(osm_val, "Far Peak")])

        with patch("app.logic.spatial.peaks._client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            result = await correct_peaks(locs, elevs)

        assert result[1] == dem_val  # unchanged

    @pytest.mark.anyio
    async def test_deviation_exactly_at_threshold(self) -> None:
        """OSM peak exactly at 10% above DEM → corrected."""
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        dem_val = 5000.0
        osm_val = dem_val * (1 + PEAK_MAX_DEVIATION)  # exactly 10%
        elevs = [500.0, dem_val, 500.0]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = _overpass_json([(osm_val, "Boundary Peak")])

        with patch("app.logic.spatial.peaks._client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            result = await correct_peaks(locs, elevs)

        assert result[1] == osm_val  # corrected

    @pytest.mark.anyio
    async def test_picks_closest_in_elevation(self) -> None:
        """Multiple OSM peaks → picks the one closest to DEM value."""
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, 5236.0, 500.0]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = _overpass_json(
            [
                (6088, "Huayna Potosi"),  # far in elevation
                (5327, "Pico Austria"),  # closest
                (5648, "Condoriri"),  # further
            ]
        )

        with patch("app.logic.spatial.peaks._client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            result = await correct_peaks(locs, elevs)

        assert result[1] == 5327.0  # closest to 5236

    @pytest.mark.anyio
    async def test_overpass_failure_returns_original(self) -> None:
        """Overpass HTTP error → graceful fallback to DEM values."""
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, 5236.0, 500.0]

        with patch("app.logic.spatial.peaks._client") as mock_client:
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("timeout"))
            result = await correct_peaks(locs, elevs)

        assert list(result) == elevs

    @pytest.mark.anyio
    async def test_empty_overpass_response(self) -> None:
        """Overpass returns no peaks → original elevations."""
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, 5236.0, 500.0]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = _overpass_json([])

        with patch("app.logic.spatial.peaks._client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            result = await correct_peaks(locs, elevs)

        assert list(result) == elevs

    @pytest.mark.anyio
    async def test_multiple_local_peaks_corrected(self) -> None:
        """Two local peaks in one trip, both get corrected."""
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, 4500.0, 1000.0, 5000.0, 500.0]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = _overpass_json(
            [
                (4600, "Peak A"),
                (5100, "Peak B"),
            ]
        )

        with patch("app.logic.spatial.peaks._client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            result = await correct_peaks(locs, elevs)

        assert result[1] == 4600.0  # closest to 4500
        assert result[3] == 5100.0  # closest to 5000
        assert result[0] == 500.0  # unchanged
        assert result[2] == 1000.0  # unchanged


# elevations (Open-Meteo DEM)


def _elev_response(values: list[float]) -> AsyncMock:
    resp = AsyncMock()
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    resp.content = json.dumps({"elevation": values}).encode()
    return resp


class TestElevations:
    @pytest.mark.anyio
    async def test_single_batch(self) -> None:
        """Fewer than 100 locations → single API call."""
        locs = [_Loc(i, i) for i in range(5)]
        expected = [100.0, 200.0, 300.0, 400.0, 500.0]

        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.get = AsyncMock(return_value=_elev_response(expected))
            result = [e async for e in elevations(locs)]

        assert result == expected
        assert mock_client.get.call_count == 1

    @pytest.mark.anyio
    async def test_multiple_batches(self) -> None:
        """More than 100 locations → multiple API calls."""
        n = OPEN_METEO_MAX_PER_REQUEST + 20  # 120
        locs = [_Loc(i, i) for i in range(n)]
        batch1 = list(range(OPEN_METEO_MAX_PER_REQUEST))
        batch2 = list(range(20))

        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.get = AsyncMock(
                side_effect=[
                    _elev_response([float(x) for x in batch1]),
                    _elev_response([float(x) for x in batch2]),
                ]
            )
            result = [e async for e in elevations(locs)]

        assert len(result) == n
        assert mock_client.get.call_count == 2

    @pytest.mark.anyio
    async def test_http_error_propagates(self) -> None:
        """HTTP errors from Open-Meteo are raised."""
        locs = [_Loc(0, 0)]

        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )

        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.get = AsyncMock(return_value=resp)
            with pytest.raises(httpx.HTTPStatusError):
                await collect_async(elevations(locs))

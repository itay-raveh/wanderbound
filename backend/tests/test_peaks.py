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
    def test_plain_string(self) -> None:
        assert _parse_ele("5327") == 5327.0

    def test_strips_meter_suffix(self) -> None:
        assert _parse_ele("5327 m") == 5327.0
        assert _parse_ele("5327m") == 5327.0

    def test_comma_decimal(self) -> None:
        assert _parse_ele("1234,5") == 1234.5

    def test_semicolon_takes_first(self) -> None:
        assert _parse_ele("5327;5300") == 5327.0

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="not a number"):
            _parse_ele("not a number")


class TestLocalPeaks:
    def test_summit_between_valleys(self) -> None:
        elevs = [500, 4000, 5200, 500]
        assert list(_local_peaks(elevs)) == [2]

    def test_high_plateau_no_prominence(self) -> None:
        elevs = [3000, 3100, 3050, 3000]
        assert list(_local_peaks(elevs)) == []

    def test_multiple_peaks(self) -> None:
        elevs = [500, 4500, 1000, 5000, 500]
        assert list(_local_peaks(elevs)) == [1, 3]

    def test_prominence_just_below_threshold(self) -> None:
        base = 1000
        elevs = [base, base + PEAK_MIN_PROMINENCE - 1, base]
        assert list(_local_peaks(elevs)) == []


class TestCorrectPeaks:
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

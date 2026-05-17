import json
from dataclasses import dataclass

import httpx
import pytest

from app.logic.spatial.peaks import (
    PEAK_MAX_DEVIATION,
    PEAK_MIN_PROMINENCE,
    _local_peaks,
    _parse_ele,
    correct_peaks,
)
from tests.helpers.http import async_client, mock_response


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


def _mock_overpass_client(peaks: list[tuple[float, str]]) -> httpx.AsyncClient:
    return async_client(post=mock_response(_overpass_json(peaks)))


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
    @pytest.mark.parametrize(
        ("middle", "peaks", "expected"),
        [
            pytest.param(
                5236.0, [(5327, "Pico Austria")], 5327.0, id="corrects-summit"
            ),
            pytest.param(5400.0, [(5327, "Pico Austria")], 5400.0, id="does-not-lower"),
            pytest.param(
                5000.0,
                [(5000.0 * (1 + PEAK_MAX_DEVIATION), "Boundary Peak")],
                5000.0 * (1 + PEAK_MAX_DEVIATION),
                id="threshold",
            ),
            pytest.param(
                5236.0,
                [
                    (6088, "Huayna Potosi"),
                    (5327, "Pico Austria"),
                    (5648, "Condoriri"),
                ],
                5327.0,
                id="closest",
            ),
        ],
    )
    async def test_peak_correction_cases(
        self, middle: float, peaks: list[tuple[float, str]], expected: float
    ) -> None:
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, middle, 500.0]

        client = _mock_overpass_client(peaks)
        result = await correct_peaks(client, locs, elevs)

        assert result == [500.0, expected, 500.0]

    async def test_overpass_failure_returns_original(self) -> None:
        locs = [_Loc(0, 0), _Loc(0, 0), _Loc(0, 0)]
        elevs = [500.0, 5236.0, 500.0]

        client = async_client(post=httpx.HTTPError("timeout"))
        result = await correct_peaks(client, locs, elevs)

        assert list(result) == elevs

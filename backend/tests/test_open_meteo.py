import datetime as _dt_mod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.core.http_clients import _open_meteo_weight
from app.services.open_meteo import (
    _LocationResult,
    _weather_from_result,
    _wmo_icon,
    build_weathers,
    elevations,
)
from tests.factories import collect_async
from tests.helpers.http import async_client, error_response, json_response


@dataclass
class _Loc:
    lat: float
    lon: float
    name: str = ""
    detail: str = ""
    country_code: str = "NL"


@dataclass
class _Step:
    location: _Loc
    timestamp: float = 0.0
    timezone_id: str = "UTC"

    @property
    def datetime(self) -> _dt_mod.datetime:
        return datetime.fromtimestamp(self.timestamp, UTC)


def _make_step(lat: float, lon: float, ts: float, **kw: Any) -> _Step:
    return _Step(location=_Loc(lat, lon), timestamp=ts, **kw)


_DAILY_FIELD_MAP = {
    "temp_max": "temperature_2m_max",
    "temp_min": "temperature_2m_min",
    "feels_max": "apparent_temperature_max",
    "feels_min": "apparent_temperature_min",
    "wmo_daily": "weather_code",
}

_DAILY_DEFAULTS: dict[str, float | int] = {
    "temperature_2m_max": 25.0,
    "temperature_2m_min": 15.0,
    "apparent_temperature_max": 27.0,
    "apparent_temperature_min": 13.0,
    "weather_code": 0,
}


def _om_response(dates: list[str], **overrides: list) -> dict:
    n = len(dates)
    daily: dict[str, list] = {"time": dates}
    for full, default in _DAILY_DEFAULTS.items():
        daily[full] = [default] * n
    for short, full in _DAILY_FIELD_MAP.items():
        if short in overrides:
            daily[full] = overrides[short]
    return {"daily": daily}


class TestElevations:
    async def test_http_error_propagates(self) -> None:
        locs = [_Loc(0, 0)]

        client = async_client(get=error_response())
        with pytest.raises(httpx.HTTPStatusError):
            await collect_async(elevations(client, locs))


class TestWmoIcon:
    @pytest.mark.parametrize(
        ("code", "night", "expected"),
        [
            (0, False, "clear-day"),
            (0, True, "clear-night"),
            (45, False, "fog-day"),
            (999, False, "not-available"),
        ],
    )
    def test_icon(self, code: int, *, night: bool, expected: str) -> None:
        assert _wmo_icon(code, night=night) == expected


class TestWeatherFromResult:
    def test_extracts_correct_day(self) -> None:
        raw = _om_response(
            ["2024-01-01", "2024-01-02"],
            temp_max=[20.0, 30.0],
            temp_min=[10.0, 18.0],
            feels_max=[22.0, 32.0],
            feels_min=[8.0, 16.0],
            wmo_daily=[0, 63],
        )
        loc = _LocationResult.model_validate(raw)
        step = _make_step(0, 0, 1704153600.0)  # 2024-01-02 UTC
        weather = _weather_from_result(step, loc)

        assert weather is not None
        assert weather.day.temp == 30.0
        assert weather.day.feels_like == 32.0
        assert weather.day.icon == "rain"
        assert weather.night is not None
        assert weather.night.temp == 18.0
        assert weather.night.feels_like == 16.0
        assert weather.night.icon == "rain"

    def test_missing_date_returns_none(self) -> None:
        raw = _om_response(["2024-01-01"])
        loc = _LocationResult.model_validate(raw)
        step = _make_step(0, 0, 1704240000.0)  # 2024-01-03 UTC
        assert _weather_from_result(step, loc) is None


class TestBuildWeathers:
    async def test_single_step(self) -> None:
        step = _make_step(52.52, 13.41, 1704067200.0)
        resp_data = _om_response(
            ["2024-01-01"],
            temp_max=[5.0],
            temp_min=[-2.0],
            feels_max=[3.0],
            feels_min=[-5.0],
            wmo_daily=[71],
        )
        client = async_client(get=json_response(resp_data))
        result = [w async for w in build_weathers(client, [step])]

        assert len(result) == 1
        idx, w = result[0]
        assert idx == 0
        assert w.day.temp == 5.0
        assert w.day.icon == "partly-cloudy-day-snow"
        assert w.night is not None
        assert w.night.temp == -2.0

    async def test_http_error_raises(self) -> None:
        step = _make_step(0, 0, 1704067200.0)
        client = async_client(get=httpx.HTTPError("fail"))
        with pytest.raises(RuntimeError, match="Weather API"):
            async for _ in build_weathers(client, [step]):
                pass


class TestOpenMeteoWeight:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (
                "https://api.open-meteo.com/v1/elevation?latitude=1.0&longitude=2.0",
                1,
            ),
            (
                "https://api.open-meteo.com/v1/elevation"
                "?latitude=1,2,3,4&longitude=5,6,7,8",
                4,
            ),
            (
                "https://archive-api.open-meteo.com/v1/archive"
                "?latitude=1&longitude=2&start_date=2024-01-01&end_date=2024-01-01"
                "&daily=temperature_2m_max,temperature_2m_min,"
                "apparent_temperature_max,apparent_temperature_min,weather_code",
                5,
            ),
            (
                "https://archive-api.open-meteo.com/v1/archive"
                "?latitude=1&longitude=2&daily=temperature_2m_max",
                1,
            ),
            (
                "https://archive-api.open-meteo.com/v1/archive?latitude=1&longitude=2",
                1,
            ),
        ],
    )
    def test_weight(self, url: str, expected: int) -> None:
        assert _open_meteo_weight(httpx.Request("GET", url)) == expected

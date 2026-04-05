"""Tests for app.services.open_meteo — elevation lookups and weather fetching."""

import datetime as _dt_mod
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.open_meteo import (
    _LocationResult,
    _weather_from_result,
    _wmo_icon,
    build_weathers,
    elevations,
)
from tests.factories import collect_async

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Weather helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Elevation tests
# ---------------------------------------------------------------------------


class TestElevations:
    async def test_http_error_propagates(self) -> None:
        locs = [_Loc(0, 0)]

        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )

        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=resp)
            with pytest.raises(httpx.HTTPStatusError):
                await collect_async(elevations(locs))


# ---------------------------------------------------------------------------
# Weather tests
# ---------------------------------------------------------------------------


class TestWmoIcon:
    def test_clear_day(self) -> None:
        assert _wmo_icon(0) == "clear-day"

    def test_clear_night(self) -> None:
        assert _wmo_icon(0, night=True) == "clear-night"

    def test_fog_day(self) -> None:
        assert _wmo_icon(45) == "fog-day"

    def test_unknown_code(self) -> None:
        assert _wmo_icon(999) == "not-available"


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
        mock_response = MagicMock(status_code=200)
        mock_response.content = json.dumps(resp_data).encode()

        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=mock_response)
            result = [w async for w in build_weathers([step])]

        assert len(result) == 1
        idx, w = result[0]
        assert idx == 0
        assert w.day.temp == 5.0
        assert w.day.icon == "partly-cloudy-day-snow"
        assert w.night is not None
        assert w.night.temp == -2.0

    async def test_http_error_raises(self) -> None:
        step = _make_step(0, 0, 1704067200.0)
        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.return_value.get = AsyncMock(
                side_effect=httpx.HTTPError("fail")
            )
            with pytest.raises(RuntimeError, match="Weather API"):
                async for _ in build_weathers([step]):
                    pass

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
    OPEN_METEO_MAX_PER_REQUEST,
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
# Elevation helpers
# ---------------------------------------------------------------------------


def _elev_response(values: list[float]) -> MagicMock:
    resp = MagicMock(status_code=200)
    resp.content = json.dumps({"elevation": values}).encode()
    return resp


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
    async def test_single_batch(self) -> None:
        locs = [_Loc(i, i) for i in range(5)]
        expected = [100.0, 200.0, 300.0, 400.0, 500.0]

        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.return_value.get = AsyncMock(
                return_value=_elev_response(expected)
            )
            result = [e async for e in elevations(locs)]

        assert result == expected
        assert mock_client.return_value.get.call_count == 1

    async def test_multiple_batches(self) -> None:
        n = OPEN_METEO_MAX_PER_REQUEST + 20  # 120
        locs = [_Loc(i, i) for i in range(n)]
        batch1 = list(range(OPEN_METEO_MAX_PER_REQUEST))
        batch2 = list(range(20))

        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.return_value.get = AsyncMock(
                side_effect=[
                    _elev_response([float(x) for x in batch1]),
                    _elev_response([float(x) for x in batch2]),
                ]
            )
            result = [e async for e in elevations(locs)]

        assert len(result) == n
        assert mock_client.return_value.get.call_count == 2

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

    def test_partly_cloudy_day(self) -> None:
        assert _wmo_icon(2) == "partly-cloudy-day"

    def test_partly_cloudy_night(self) -> None:
        assert _wmo_icon(2, night=True) == "partly-cloudy-night"

    def test_moderate_rain(self) -> None:
        assert _wmo_icon(63) == "rain"

    def test_moderate_rain_night(self) -> None:
        assert _wmo_icon(63, night=True) == "rain"

    def test_slight_rain_day(self) -> None:
        assert _wmo_icon(61) == "partly-cloudy-day-rain"

    def test_slight_rain_night(self) -> None:
        assert _wmo_icon(61, night=True) == "partly-cloudy-night-rain"

    def test_thunderstorm_day(self) -> None:
        assert _wmo_icon(95) == "thunderstorms-day"

    def test_thunderstorm_night(self) -> None:
        assert _wmo_icon(95, night=True) == "thunderstorms-night"

    def test_overcast_day(self) -> None:
        assert _wmo_icon(3) == "overcast-day"

    def test_overcast_night(self) -> None:
        assert _wmo_icon(3, night=True) == "overcast-night"

    def test_snow(self) -> None:
        assert _wmo_icon(73) == "snow"

    def test_fog_day(self) -> None:
        assert _wmo_icon(45) == "fog-day"

    def test_fog_night(self) -> None:
        assert _wmo_icon(45, night=True) == "fog-night"

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
    async def test_empty_steps(self) -> None:
        assert [w async for w in build_weathers([])] == []

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

    async def test_multiple_steps_routed_by_date(self) -> None:
        s1 = _make_step(52.52, 13.41, 1704067200.0)  # Jan 1
        s2 = _make_step(48.85, 2.35, 1704153600.0)  # Jan 2
        resp1 = _om_response(["2024-01-01"], temp_max=[5.0], wmo_daily=[73])
        resp2 = _om_response(["2024-01-02"], temp_max=[12.0], wmo_daily=[63])

        responses = {"2024-01-01": resp1, "2024-01-02": resp2}

        async def _route(_url: Any, *, params: dict[str, Any]) -> MagicMock:
            r = MagicMock(status_code=200)
            r.content = json.dumps(responses[params["start_date"]]).encode()
            return r

        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.return_value.get = AsyncMock(side_effect=_route)
            result = dict([w async for w in build_weathers([s1, s2])])

        assert len(result) == 2
        assert result[0].day.temp == 5.0
        assert result[0].day.icon == "snow"
        assert result[1].day.temp == 12.0
        assert result[1].day.icon == "rain"

    async def test_http_error_raises(self) -> None:
        step = _make_step(0, 0, 1704067200.0)
        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.return_value.get = AsyncMock(
                side_effect=httpx.HTTPError("fail")
            )
            with pytest.raises(RuntimeError, match="Weather API"):
                async for _ in build_weathers([step]):
                    pass

    async def test_night_uses_daily_code(self) -> None:
        step = _make_step(52.52, 13.41, 1704067200.0)
        resp_data = _om_response(["2024-01-01"], wmo_daily=[63])
        mock_response = MagicMock(status_code=200)
        mock_response.content = json.dumps(resp_data).encode()

        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=mock_response)
            result = dict([w async for w in build_weathers([step])])

        assert result[0].day.icon == "rain"
        assert result[0].night is not None
        assert result[0].night.icon == "rain"

    async def test_429_raises(self) -> None:
        step = _make_step(0, 0, 1704067200.0)
        mock_response = MagicMock(status_code=429)
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429", request=MagicMock(), response=mock_response
        )

        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=mock_response)
            with pytest.raises(RuntimeError, match="Weather API error"):
                async for _ in build_weathers([step]):
                    pass

    async def test_multiple_steps_own_api_call(self) -> None:
        steps = [_make_step(i, i, 1720990800.0) for i in range(3)]
        resp_data = _om_response(
            ["2024-07-14"],
            temp_max=[25.0],
            temp_min=[15.0],
            feels_max=[27.0],
            feels_min=[13.0],
            wmo_daily=[1],
        )
        mock_response = MagicMock(status_code=200)
        mock_response.content = json.dumps(resp_data).encode()

        with patch("app.services.open_meteo._client") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=mock_response)
            result = [w async for w in build_weathers(steps)]

        assert len(result) == 3
        assert mock_client.return_value.get.call_count == 3

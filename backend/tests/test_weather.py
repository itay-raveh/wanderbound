"""Tests for Open-Meteo weather fetching and WMO code mapping."""

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.logic.weather import (
    _LocationResult,
    _weather_from_result,
    _wmo_icon,
    build_weathers,
)

# ── Helpers ─────────────────────────────────────────────────────────────


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
    weather_temperature: float = 20.0
    weather_condition: str = "clear-day"
    timestamp: float = 0.0
    timezone_id: str = "UTC"

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, UTC)


def _make_step(lat: float, lon: float, ts: float, **kw: object) -> _Step:
    return _Step(location=_Loc(lat, lon), timestamp=ts, **kw)


def _om_response(  # noqa: PLR0913
    dates: list[str],
    *,
    temp_max: list[float] | None = None,
    temp_min: list[float] | None = None,
    feels_max: list[float] | None = None,
    feels_min: list[float] | None = None,
    wmo_daily: list[int] | None = None,
) -> dict:
    n = len(dates)
    return {
        "daily": {
            "time": dates,
            "temperature_2m_max": temp_max or [25.0] * n,
            "temperature_2m_min": temp_min or [15.0] * n,
            "apparent_temperature_max": feels_max or [27.0] * n,
            "apparent_temperature_min": feels_min or [13.0] * n,
            "weather_code": wmo_daily or [0] * n,
        },
    }


# ── _wmo_icon ───────────────────────────────────────────────────────────


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


# ── _weather_from_result ────────────────────────────────────────────────


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


# ── build_weathers ──────────────────────────────────────────────────────


class TestBuildWeathers:
    @pytest.mark.anyio
    async def test_empty_steps(self) -> None:
        assert [w async for w in build_weathers([])] == []

    @pytest.mark.anyio
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
        mock_response.json.return_value = resp_data

        with patch("app.logic.weather.client") as mc:
            mc.get = AsyncMock(return_value=mock_response)
            result = [w async for w in build_weathers([step])]

        assert len(result) == 1
        assert result[0].day.temp == 5.0
        assert result[0].day.icon == "partly-cloudy-day-snow"
        assert result[0].night is not None
        assert result[0].night.temp == -2.0

    @pytest.mark.anyio
    async def test_multiple_steps(self) -> None:
        s1 = _make_step(52.52, 13.41, 1704067200.0)  # Jan 1
        s2 = _make_step(48.85, 2.35, 1704153600.0)  # Jan 2
        resp1 = _om_response(["2024-01-01"], temp_max=[5.0], wmo_daily=[73])
        resp2 = _om_response(["2024-01-02"], temp_max=[12.0], wmo_daily=[63])

        mock_r1 = MagicMock(status_code=200)
        mock_r1.json.return_value = resp1
        mock_r2 = MagicMock(status_code=200)
        mock_r2.json.return_value = resp2

        with patch("app.logic.weather.client") as mc:
            mc.get = AsyncMock(side_effect=[mock_r1, mock_r2])
            result = [w async for w in build_weathers([s1, s2])]

        assert len(result) == 2
        assert result[0].day.temp == 5.0
        assert result[0].day.icon == "snow"
        assert result[1].day.temp == 12.0
        assert result[1].day.icon == "rain"

    @pytest.mark.anyio
    async def test_http_error_raises(self) -> None:
        step = _make_step(0, 0, 1704067200.0)
        with patch("app.logic.weather.client") as mc:
            mc.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
            with pytest.raises(RuntimeError, match="Weather API"):
                async for _ in build_weathers([step]):
                    pass

    @pytest.mark.anyio
    async def test_night_uses_daily_code(self) -> None:
        step = _make_step(52.52, 13.41, 1704067200.0)
        resp_data = _om_response(["2024-01-01"], wmo_daily=[63])
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = resp_data

        with patch("app.logic.weather.client") as mc:
            mc.get = AsyncMock(return_value=mock_response)
            result = [w async for w in build_weathers([step])]

        assert result[0].day.icon == "rain"
        assert result[0].night is not None
        assert result[0].night.icon == "rain"

    @pytest.mark.anyio
    async def test_429_raises(self) -> None:
        step = _make_step(0, 0, 1704067200.0)
        mock_response = MagicMock(status_code=429)

        with patch("app.logic.weather.client") as mc:
            mc.get = AsyncMock(return_value=mock_response)
            with pytest.raises(RuntimeError, match="Weather API returned 429"):
                async for _ in build_weathers([step]):
                    pass

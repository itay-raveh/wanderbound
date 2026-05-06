"""Tests for app.logic.trip_processing."""

from __future__ import annotations

from app.logic.trip_processing import (
    default_media_resolution_warning_preset,
    resolve_international_waters,
    segment_timezone,
)
from app.models.polarsteps import Location, PSStep
from app.models.user import User


class TestDefaultMediaResolutionWarningPreset:
    def test_uses_relaxed_warnings_for_normal_users(self) -> None:
        user = User(
            id=1,
            first_name="Test",
            locale="en-US",
            unit_is_km=True,
            temperature_is_celsius=True,
            google_sub="test-sub",
        )

        assert default_media_resolution_warning_preset(user) == "relaxed"

    def test_disables_warnings_for_demo_users(self) -> None:
        user = User(
            id=1,
            first_name="Demo",
            locale="en-US",
            unit_is_km=True,
            temperature_is_celsius=True,
            is_demo=True,
        )

        assert default_media_resolution_warning_preset(user) == "off"


def _step(name: str, country_code: str, timestamp: float = 0) -> PSStep:
    return PSStep(
        id=int(timestamp),
        name=name,
        slug=name.lower().replace(" ", "-"),
        description="",
        timestamp=timestamp,
        timezone_id="UTC",
        location=Location(
            name=name, detail="", country_code=country_code, lat=0, lon=0
        ),
    )


class TestResolveInternationalWaters:
    def test_replaces_with_previous_code(self) -> None:
        steps = [
            _step("Tortuga Bay", "EC", 1),
            _step("Gordon Rocks", "00", 2),
            _step("Camino de Tortugas", "EC", 3),
        ]
        resolve_international_waters(steps)
        assert steps[1].location.country_code == "ec"

    def test_multiple_consecutive_zeros(self) -> None:
        steps = [
            _step("Naples", "IT", 1),
            _step("At Sea 1", "00", 2),
            _step("At Sea 2", "00", 3),
            _step("Sorrento", "IT", 4),
        ]
        resolve_international_waters(steps)
        assert steps[1].location.country_code == "it"
        assert steps[2].location.country_code == "it"

    def test_attribution_when_next_country_differs(self) -> None:
        steps = [
            _step("Piraeus", "GR", 1),
            _step("At Sea", "00", 2),
            _step("Kusadasi", "TR", 3),
        ]
        resolve_international_waters(steps)

        assert steps[1].location.country_code == "gr"

    def test_leading_zeros_unchanged(self) -> None:
        steps = [
            _step("At Sea", "00", 1),
            _step("Naples", "IT", 2),
        ]
        resolve_international_waters(steps)
        assert steps[0].location.country_code == "00"

    def test_trailing_zeros(self) -> None:
        steps = [
            _step("Naples", "IT", 1),
            _step("At Sea", "00", 2),
        ]
        resolve_international_waters(steps)
        assert steps[1].location.country_code == "it"


class TestSegmentTimezone:
    def test_picks_step_before_segment_start(self) -> None:
        steps = [
            _step("A", "CL", 100),
            _step("B", "CL", 200),
            _step("C", "CL", 400),
        ]
        steps[0].timezone_id = "America/Santiago"
        steps[1].timezone_id = "America/Santiago"
        steps[2].timezone_id = "America/Buenos_Aires"
        assert segment_timezone(250, steps) == "America/Santiago"

    def test_falls_back_to_first_step(self) -> None:
        steps = [_step("A", "CL", 500)]
        steps[0].timezone_id = "America/Santiago"
        assert segment_timezone(100, steps) == "America/Santiago"

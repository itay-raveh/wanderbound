"""Tests for app.logic.processing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from app.logic.processing import (
    resolve_international_waters,
    segment_timezone,
)
from app.models.polarsteps import Location, PSStep


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

    def test_warns_when_next_country_differs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        steps = [
            _step("Piraeus", "GR", 1),
            _step("At Sea", "00", 2),
            _step("Kusadasi", "TR", 3),
        ]
        with caplog.at_level(logging.WARNING):
            resolve_international_waters(steps)

        assert steps[1].location.country_code == "gr"
        assert "At Sea" in caplog.text
        assert "GR" in caplog.text
        assert "TR" in caplog.text

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

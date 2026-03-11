"""Integration tests for build_segments using real Polarsteps trip data.

Uses the South America 2024-2025 trip to verify segmentation against
known ground truth (hike times, structural invariants).

All tests build segments from the full trip (all steps + all GPS points),
matching how segments are pre-computed at user creation time.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest

from app.logic.spatial.segments import SegmentKind, build_segments

if TYPE_CHECKING:
    from app.logic.spatial.segments import SegmentData
    from app.models.trips import Locations, Trip

# Tolerance for hike start/end times: GPS can be sparse so allow ±30 min.
_TOL_S = 30 * 60


def _cmp(ts: float, dt_str: str, tz: ZoneInfo) -> float:
    """Return signed error (seconds) vs expected 'YYYY-MM-DD HH:MM' in tz."""
    ref = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    return ts - ref.timestamp()


@pytest.fixture(scope="module")
def all_segments(sa_trip: Trip, sa_locations: Locations) -> list[SegmentData]:
    """Build segments once from the full trip (all steps + GPS)."""
    steps = sorted(sa_trip.all_steps, key=lambda s: s.timestamp)
    return list(build_segments(steps, sa_locations.locations))


def _hikes_in_window(
    segments: list[SegmentData],
    steps: list,
    start: int,
    end: int,
) -> list[SegmentData]:
    """Return hike segments whose midpoint falls within the step range's day window."""
    t0 = (
        steps[start]
        .datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        .timestamp()
    )
    t1 = (
        steps[end]
        .datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
        .timestamp()
    )
    return [
        s
        for s in segments
        if s.kind == SegmentKind.hike
        and t0 <= (s.points[0].time + s.points[-1].time) / 2 <= t1
    ]


class TestKnownHikes:
    """Verify detected hikes match known ground truth times.

    Segments are built once from the full trip.  For each test case the hikes
    whose midpoint falls inside the step range's day window are checked against
    expected ground truth start/end times.
    """

    @pytest.mark.parametrize(
        ("start", "end", "expected_hikes"),
        [
            (1, 2, [("2024-11-14 12:30", "2024-11-14 16:30")]),
            (5, 5, [("2024-11-17 08:00", "2024-11-17 21:00")]),
            (6, 6, [("2024-11-19 11:30", "2024-11-19 18:30")]),
            (7, 7, [("2024-11-21 11:00", "2024-11-21 19:30")]),
            (8, 8, [("2024-11-23 12:00", "2024-11-23 17:30")]),
            (9, 9, [("2024-11-27 11:30", "2024-11-27 17:30")]),
            (10, 12, []),
            (12, 16, [("2024-12-01 11:30", "2024-12-04 18:00")]),
            (18, 21, [("2024-12-08 11:30", "2024-12-11 15:30")]),
        ],
    )
    def test_hike_times(
        self,
        start: int,
        end: int,
        expected_hikes: list[tuple[str, str]],
        sa_trip: Trip,
        all_segments: list[SegmentData],
    ) -> None:
        steps = sa_trip.all_steps
        tz_start = ZoneInfo(steps[start].timezone_id)
        tz_end = ZoneInfo(steps[end].timezone_id)

        hikes = _hikes_in_window(all_segments, steps, start, end)

        assert len(hikes) == len(expected_hikes), [s.kind for s in hikes]

        for hike, (exp_start, exp_end) in zip(hikes, expected_hikes, strict=True):
            act_start = hike.points[0].time
            act_end = hike.points[-1].time
            act_start_local = datetime.fromtimestamp(act_start, tz_start)
            act_end_local = datetime.fromtimestamp(act_end, tz_end)
            assert abs(_cmp(act_start, exp_start, tz_start)) <= _TOL_S, (
                f"Hike start: expected {exp_start} {tz_start} ±30min, "
                f"got {act_start_local.strftime('%Y-%m-%d %H:%M')}"
            )
            assert abs(_cmp(act_end, exp_end, tz_end)) <= _TOL_S, (
                f"Hike end: expected {exp_end} {tz_end} ±30min, "
                f"got {act_end_local.strftime('%Y-%m-%d %H:%M')}"
            )


class TestFullTripInvariants:
    """Structural invariants verified against the full trip."""

    def test_min_points_per_segment(self, all_segments: list[SegmentData]) -> None:
        for i, seg in enumerate(all_segments):
            expected_min = (
                2 if seg.kind in (SegmentKind.hike, SegmentKind.flight) else 1
            )
            assert len(seg.points) >= expected_min, f"Segment {i} ({seg.kind})"

    def test_no_other_kind(self, all_segments: list[SegmentData]) -> None:
        """Regression: internal 'other' label was exposed to callers."""
        assert all(s.kind.value != "other" for s in all_segments)

    def test_contiguous_boundaries(
        self, all_segments: list[SegmentData], sa_trip: Trip
    ) -> None:
        tz = ZoneInfo(sa_trip.all_steps[1].timezone_id)
        for i in range(len(all_segments) - 1):
            t_end = all_segments[i].points[-1].time
            t_start = all_segments[i + 1].points[0].time
            assert t_end == t_start, (
                f"Gap between seg {i} ({all_segments[i].kind}) and {i + 1}: "
                f"{(t_start - t_end) / 3600:.2f}h at "
                f"{datetime.fromtimestamp(t_end, tz).strftime('%Y-%m-%d %H:%M %Z')}"
            )

    def test_hikes_are_simplified(self, all_segments: list[SegmentData]) -> None:
        """Hike segments are RDP-simplified but retain at least 2 points."""
        hikes = [s for s in all_segments if s.kind == SegmentKind.hike]
        assert hikes
        for i, h in enumerate(hikes):
            assert len(h.points) >= 2, f"Hike {i} has only {len(h.points)} points"


class TestStepLocationInHike:
    def test_step9_location_in_output(
        self, sa_trip: Trip, all_segments: list[SegmentData]
    ) -> None:
        """Step 9 (Ushuaia viewpoint) must appear in the hike output.

        Regression: RDP collapsed out-and-back paths to two endpoints.
        """
        step9 = sa_trip.all_steps[9]
        hikes = [s for s in all_segments if s.kind == SegmentKind.hike]

        in_hike = any(
            abs(p.lat - step9.location.lat) < 0.001
            and abs(p.lon - step9.location.lon) < 0.001
            for h in hikes
            for p in h.points
        )
        assert in_hike, (
            f"Step 9 ({step9.location.lat:.4f}, {step9.location.lon:.4f})"
            " not in any hike"
        )

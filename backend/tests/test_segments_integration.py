"""Integration tests for build_segments using real Polarsteps trip data.

Uses the South America 2024-2025 trip to verify segmentation against
known ground truth (hike times, structural invariants).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest

from app.logic.spatial.segments import SegmentKind, build_segments

if TYPE_CHECKING:
    from app.logic.spatial.segments import Segment
    from app.models.trips import Locations, Trip

# Tolerance for hike start/end times: GPS can be sparse so allow ±30 min.
_TOL_S = 30 * 60


def _cmp(ts: float, dt_str: str, tz: ZoneInfo) -> float:
    """Return signed error (seconds) vs expected 'YYYY-MM-DD HH:MM' in tz."""
    ref = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    return ts - ref.timestamp()


class TestKnownHikes:
    """Verify detected hikes match known ground truth times."""

    @pytest.mark.parametrize(
        ("start", "end", "expected_hikes"),
        [
            (1, 2, [("2024-11-14 12:30", "2024-11-14 16:30")]),
            (5, 5, [("2024-11-17 08:00", "2024-11-17 21:00")]),
            (6, 6, [("2024-11-19 11:30", "2024-11-19 18:30")]),
            (7, 7, [("2024-11-21 11:00", "2024-11-21 19:30")]),
            (8, 8, [("2024-11-23 11:30", "2024-11-23 17:30")]),
            (9, 9, [("2024-11-27 11:30", "2024-11-27 17:30")]),
            (10, 12, []),
            (12, 16, [("2024-12-01 11:30", "2024-12-04 18:00")]),
            (17, 17, []),
            (18, 21, [("2024-12-08 11:30", "2024-12-11 15:30")]),
        ],
    )
    def test_hike_times(
        self,
        start: int,
        end: int,
        expected_hikes: list[tuple[str, str]],
        sa_trip: Trip,
        sa_locations: Locations,
    ) -> None:
        steps = sa_trip.all_steps
        tz_start = ZoneInfo(steps[start].timezone_id)
        tz_end = ZoneInfo(steps[end].timezone_id)

        segments = list(build_segments(steps[start : end + 1], sa_locations.locations))
        hikes = [s for s in segments if s.kind == SegmentKind.hike]

        assert len(hikes) == len(expected_hikes), [s.kind for s in segments]

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
    """Structural invariants verified against steps 1–22 of the real trip."""

    @pytest.fixture()
    def segments(self, sa_trip: Trip, sa_locations: Locations) -> list[Segment]:
        steps = sorted(sa_trip.all_steps, key=lambda s: s.timestamp)[1:23]
        return list(build_segments(steps, sa_locations.locations))

    def test_min_points_per_segment(self, segments: list[Segment]) -> None:
        for i, seg in enumerate(segments):
            expected_min = 2 if seg.kind in (SegmentKind.hike, SegmentKind.flight) else 1
            assert len(seg.points) >= expected_min, f"Segment {i} ({seg.kind})"

    def test_no_other_kind(self, segments: list[Segment]) -> None:
        """Regression: internal 'other' label was exposed to callers."""
        assert all(s.kind.value != "other" for s in segments)

    def test_contiguous_boundaries(self, segments: list[Segment], sa_trip: Trip) -> None:
        tz = ZoneInfo(sa_trip.all_steps[1].timezone_id)
        for i in range(len(segments) - 1):
            t_end = segments[i].points[-1].time
            t_start = segments[i + 1].points[0].time
            assert t_end == t_start, (
                f"Gap between seg {i} ({segments[i].kind}) and {i + 1}: "
                f"{(t_start - t_end) / 3600:.2f}h at "
                f"{datetime.fromtimestamp(t_end, tz).strftime('%Y-%m-%d %H:%M %Z')}"
            )

    def test_hikes_keep_all_points(self, segments: list[Segment]) -> None:
        """Regression: hike segments were RDP-simplified, losing elevation accuracy."""
        hikes = [s for s in segments if s.kind == SegmentKind.hike]
        assert hikes
        for i, h in enumerate(hikes):
            assert len(h.points) > 10, f"Hike {i} has only {len(h.points)} points"


class TestStepLocationInHike:
    def test_step9_location_in_output(self, sa_trip: Trip, sa_locations: Locations) -> None:
        """Step 9 (Ushuaia viewpoint) must appear in the hike output.

        Regression: RDP collapsed out-and-back paths to two endpoints.
        """
        steps = sa_trip.all_steps
        step9 = steps[9]
        segments = list(build_segments(steps[9:10], sa_locations.locations))
        hikes = [s for s in segments if s.kind == SegmentKind.hike]
        assert hikes

        in_hike = any(
            abs(p.lat - step9.location.lat) < 0.001 and abs(p.lon - step9.location.lon) < 0.001
            for p in hikes[0].points
        )
        assert in_hike, (
            f"Step 9 ({step9.location.lat:.4f}, {step9.location.lon:.4f}) not in hike points"
        )

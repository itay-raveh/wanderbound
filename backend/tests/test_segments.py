"""Integration tests for build_segments using real Polarsteps trip data.

These tests load actual trip.json and locations.json from the test_data directory
and verify that the segmentation pipeline produces correct results matching
known ground truth about the trip.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest

from app.logic.spatial.segments import SegmentKind, build_segments

if TYPE_CHECKING:
    from app.models.trips import Locations, Trip

# Tolerance for hike start/end times: GPS can be sparse so allow ±30 min.
_TOL_S = 30 * 60


def _cmp(ts: float, dt_str: str, tz: ZoneInfo) -> float:
    """Return signed error (seconds) vs expected 'YYYY-MM-DD HH:MM' in tz."""
    ref = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    return ts - ref.timestamp()


# Each entry: (start_step, end_step, [(hike_start, hike_end), ...]).
# Times are "YYYY-MM-DD HH:MM" in the local timezone of steps[start] / steps[end].
# Empty list means the window should produce no hikes.
@pytest.mark.parametrize(
    ("start", "end", "expected_hikes"),
    [
        (1, 2, [("2024-11-14 12:30", "2024-11-14 16:30")]),  # fill in real local times
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
def test_known_hikes(
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


def test_steps_1_to_22_no_gaps(sa_trip: Trip, sa_locations: Locations) -> None:
    """All hike and flight segments should have at least 2 points."""
    steps = sorted(sa_trip.all_steps, key=lambda s: s.timestamp)[1:23]
    segments = list(build_segments(steps, sa_locations.locations))

    for i, seg in enumerate(segments):
        if seg.kind in (SegmentKind.hike, SegmentKind.flight):
            assert len(seg.points) >= 2, (
                f"Segment {i} ({seg.kind}) has only {len(seg.points)} point(s)"
            )
        else:
            assert len(seg.points) >= 1, f"Segment {i} ({seg.kind}) is erroneously empty"


def test_no_other_kind_in_full_trip(sa_trip: Trip, sa_locations: Locations) -> None:
    """``build_segments`` must never emit a segment with kind == 'other'.

    Regression: before the walking/driving split, the internal ``"other"``
    label was exposed directly to callers.
    """
    steps = sorted(sa_trip.all_steps, key=lambda s: s.timestamp)[1:23]
    segments = list(build_segments(steps, sa_locations.locations))
    other = [s for s in segments if s.kind.value == "other"]
    assert not other, f"Found {len(other)} unexpected 'other' segment(s)"


def test_step_location_in_hike_step9(sa_trip: Trip, sa_locations: Locations) -> None:
    """Step 9 (Ushuaia mountain viewpoint) must appear in the hike output points.

    Regression: on out-and-back routes RDP used to collapse the path to its
    two endpoints, dropping the turnaround point at the step's location.
    """
    steps = sa_trip.all_steps
    step9 = steps[9]
    segments = list(build_segments(steps[9:10], sa_locations.locations))
    hikes = [s for s in segments if s.kind == SegmentKind.hike]
    assert hikes, "Expected at least one hike for step 9"
    in_hike = any(
        abs(p.lat - step9.location.lat) < 0.001 and abs(p.lon - step9.location.lon) < 0.001
        for p in hikes[0].points
    )
    assert in_hike, (
        f"Step 9 location ({step9.location.lat:.4f}, {step9.location.lon:.4f}) "
        f"not found in hike points"
    )


def test_hike_segments_keep_all_points(sa_trip: Trip, sa_locations: Locations) -> None:
    """Hike segments must not be RDP-simplified.

    Regression: hike segments were previously passed through RDP, which
    discarded intermediate points needed for accurate distance calculations.
    All hike segments for steps 1–22 should have many points (> 10).
    """
    steps = sorted(sa_trip.all_steps, key=lambda s: s.timestamp)[1:23]
    segments = list(build_segments(steps, sa_locations.locations))
    hikes = [s for s in segments if s.kind == SegmentKind.hike]
    assert hikes
    for i, h in enumerate(hikes):
        assert len(h.points) > 10, (
            f"Hike {i} has only {len(h.points)} points — may have been RDP-simplified"
        )


def test_segments_are_contiguous(sa_trip: Trip, sa_locations: Locations) -> None:
    """Consecutive segments must share their boundary point — no spatial or temporal gaps."""
    steps = sorted(sa_trip.all_steps, key=lambda s: s.timestamp)[1:23]
    tz = ZoneInfo(steps[0].timezone_id)
    segments = list(build_segments(steps, sa_locations.locations))

    for i in range(len(segments) - 1):
        last_pt = segments[i].points[-1]
        first_pt = segments[i + 1].points[0]
        assert last_pt.time == first_pt.time, (
            f"Gap between seg {i} ({segments[i].kind}) ending "
            f"{datetime.fromtimestamp(last_pt.time, tz).strftime('%Y-%m-%d %H:%M %Z')} "
            f"and seg {i + 1} ({segments[i + 1].kind}) starting "
            f"{datetime.fromtimestamp(first_pt.time, tz).strftime('%Y-%m-%d %H:%M %Z')} "
            f"({(first_pt.time - last_pt.time) / 3600:.2f}h)"
        )

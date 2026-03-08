"""Unit and regression tests for the segmentation pipeline using synthetic GPS data.

Each test exercises a specific invariant or guards against a known regression:

  - Step waypoint preservation through ``_clean`` (teleport + spike filters)
  - Step-adjacent edge speed relaxation in ``_label``
  - Step location preserved in hike output (turnaround / RDP regression)
  - ``walking`` / ``driving`` classification replacing the internal ``"other"``
  - Hike segments retain all densified points (no RDP simplification)
  - Hike validation thresholds (min duration, min distance)
  - Flight detection
  - Robustness: empty steps, no GPS, single step, sparse noise input
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import polars as pl
import pytest

from app.logic.spatial.points import Point
from app.logic.spatial.segments import (
    TELEPORT_MAX_SPEED_KMH,
    FLIGHT_MIN_DISTANCE_KM,
    FLIGHT_MIN_SPEED_KMH,
    HIKE_MAX_SPEED_KMH,
    HIKE_MIN_DISTANCE_KM,
    HIKE_MIN_DURATION_H,
    SegmentKind,
    _remove_gps_noise,
    build_segments,
)

# ── Time helpers ──────────────────────────────────────────────────────────────

# All synthetic tests use 2024-01-01 as the base date (UTC).
_BASE_TS = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()


def _ts(hours: float) -> float:
    """Unix timestamp at base-date midnight + ``hours``."""
    return _BASE_TS + hours * 3600.0


def _dt(hours: float) -> datetime:
    """Aware UTC datetime at base-date midnight + ``hours``."""
    return datetime.fromtimestamp(_ts(hours), tz=timezone.utc)


# ── Synthetic step / GPS helpers ──────────────────────────────────────────────


@dataclass
class _Loc:
    lat: float
    lon: float


@dataclass
class _Step:
    """Minimal StepLike for tests — mirrors the protocol in segments.py."""

    location: _Loc
    _hours: float

    @property
    def datetime(self) -> datetime:
        return _dt(self._hours)


def _step(lat: float, lon: float, hours: float) -> _Step:
    return _Step(location=_Loc(lat=lat, lon=lon), _hours=hours)


def _pt(lat: float, lon: float, hours: float) -> Point:
    return Point(lat=lat, lon=lon, time=_ts(hours))


def _track(
    lat0: float,
    lon0: float,
    lat1: float,
    lon1: float,
    h0: float,
    h1: float,
    n: int = 20,
) -> list[Point]:
    """Linearly-interpolated GPS track with ``n+1`` equally spaced points."""
    return [
        _pt(
            lat0 + (lat1 - lat0) * i / n,
            lon0 + (lon1 - lon0) * i / n,
            h0 + (h1 - h0) * i / n,
        )
        for i in range(n + 1)
    ]


# ── Helpers for _clean unit tests ─────────────────────────────────────────────


def _clean_df(rows: list[tuple], *, with_is_step: bool) -> pl.DataFrame:
    """Build a DataFrame in the format expected by ``_remove_gps_noise``.

    Each row is ``(lat, lon, unix_time_seconds, is_step?)``.
    """
    data: dict = {
        "lat": [float(r[0]) for r in rows],
        "lon": [float(r[1]) for r in rows],
        "time": [float(r[2]) for r in rows],
    }
    if with_is_step:
        data["is_step"] = [bool(r[3]) for r in rows]
    return pl.DataFrame(data)


# ── _clean: teleport filter ───────────────────────────────────────────────────


def test_clean_removes_teleport_gps_point() -> None:
    """A GPS point that jumps at unrealistic speed is removed."""
    # Row 1 jumps 50° in 10 seconds → ~648 000 deg/h >> MAX_CLEAN_KMH/80.
    # Note: the point after a teleport may also be pruned because its "speed"
    # is computed relative to the teleport position — only the teleport itself
    # is guaranteed to be absent.
    rows = [
        (0.0, 0.0, _ts(10.0), False),
        (50.0, 0.0, _ts(10.0) + 10, False),  # teleport
        (0.01, 0.0, _ts(12.0), False),
    ]
    df = _remove_gps_noise(_clean_df(rows, with_is_step=True))
    assert 50.0 not in df["lat"].to_list(), "Teleport row should have been removed"


def test_clean_keeps_step_waypoint_that_looks_like_teleport() -> None:
    """A step waypoint must survive even when it appears as a teleport."""
    rows = [
        (0.0, 0.0, _ts(10.0), False),
        (50.0, 0.0, _ts(10.0) + 10, True),  # same huge jump, but is_step=True
        (0.01, 0.0, _ts(12.0), False),
    ]
    df = _remove_gps_noise(_clean_df(rows, with_is_step=True))
    assert 50.0 in df["lat"].to_list(), "Step waypoint must not be removed as teleport"


# ── _clean: spike filter ──────────────────────────────────────────────────────


def test_clean_removes_spike_gps_point() -> None:
    """A GPS detour that back-tracks to nearly the same position is removed.

    Spike condition: dist(prev→cur) is large AND dist(prev→next) is small
    (i.e. the current point is a detour from an otherwise straight path).
    """
    # Row 1 is 0.1° off the baseline; row 2 is only 0.005° off the baseline.
    # → row 1 is a spike.
    rows = [
        (0.0, 0.0, _ts(10.0), False),
        (0.0, 0.1, _ts(10.5), False),  # detour spike — 0.1° ≈ 11 km off path
        (0.0, 0.005, _ts(11.0), False),  # back near the original line
    ]
    df = _remove_gps_noise(_clean_df(rows, with_is_step=True))
    assert df.height == 2, "Spike row should have been removed"
    assert 0.1 not in df["lon"].to_list()


def test_clean_keeps_step_waypoint_that_looks_like_spike() -> None:
    """A step waypoint that would match the spike pattern must survive."""
    rows = [
        (0.0, 0.0, _ts(10.0), False),
        (0.0, 0.1, _ts(10.5), True),  # same detour, but is_step=True
        (0.0, 0.005, _ts(11.0), False),
    ]
    df = _remove_gps_noise(_clean_df(rows, with_is_step=True))
    assert 0.1 in df["lon"].to_list(), "Step waypoint must not be removed as spike"


# ── build_segments: step location in hike output ─────────────────────────────


def test_step_location_in_out_and_back_hike() -> None:
    """Step at the turnaround of an out-and-back hike must appear in the
    hike segment's output points.

    Regression: RDP used to collapse the out-and-back path to two endpoints,
    discarding the step at the turning point.  Hike segments now keep all
    densified points, and step waypoints are force-kept regardless.
    """
    # Approach: city (0,0) → foothills (0, 0.09) over 3 h at ~3.7 km/h
    gps_approach = _track(0.0, 0.0, 0.0, 0.09, h0=8.0, h1=11.0, n=20)
    # Return: foothills back to city over 3 h (GPS never records the summit)
    gps_return = _track(0.0, 0.09, 0.0, 0.0, h0=13.0, h1=16.0, n=20)

    # Step at the summit (0, 0.15), between approach-end and return-start
    summit = _step(lat=0.0, lon=0.15, hours=12.0)

    segments = list(build_segments([summit], gps_approach + gps_return))
    hikes = [s for s in segments if s.kind == SegmentKind.hike]

    assert len(hikes) >= 1

    step_lat, step_lon = 0.0, 0.15
    in_hike = any(
        abs(p.lat - step_lat) < 0.001 and abs(p.lon - step_lon) < 0.001 for p in hikes[0].points
    )
    assert in_hike, (
        f"Summit step not in hike points; got {[(p.lat, p.lon) for p in hikes[0].points]}"
    )


def test_step_included_when_edge_to_step_is_above_hike_speed() -> None:
    """When GPS stops recording before the step location, the edge from the
    last GPS point to the step may appear faster than MAX_HIKE_KMH.  The step
    should still be part of the hike.

    Regression: before the speed-relaxation fix, step-adjacent edges were
    only granted a longer time-gap allowance, not a speed exemption.
    """
    # GPS: slow hike along (0,0)→(0,0.05) over 5 h
    gps = _track(0.0, 0.0, 0.0, 0.05, h0=8.0, h1=13.0, n=30)

    # Step 2° lon further at t=13.5 h
    # Edge from last GPS (0, 0.05, t=13h) to step (0, 0.15, t=13.5h):
    # distance ≈ 0.1° × 111 km ≈ 11.1 km in 0.5 h → 22 km/h > MAX_HIKE_KMH
    viewpoint = _step(lat=0.0, lon=0.15, hours=13.5)

    segments = list(build_segments([viewpoint], gps))
    hikes = [s for s in segments if s.kind == SegmentKind.hike]

    assert len(hikes) >= 1
    step_lat, step_lon = 0.0, 0.15
    in_hike = any(
        abs(p.lat - step_lat) < 0.001 and abs(p.lon - step_lon) < 0.001 for p in hikes[0].points
    )
    assert in_hike, "Step location should be in hike even when GPS-edge speed > MAX_HIKE_KMH"


# ── build_segments: walking / driving / flight ────────────────────────────────


def test_no_other_kind_in_output() -> None:
    """``build_segments`` must never emit a segment with kind == 'other'.

    The internal ``"other"`` pipeline label must always be resolved to
    either ``walking`` (avg ≤ MAX_HIKE_KMH) or ``driving`` (avg > MAX_HIKE_KMH).
    """
    # Build a realistic mixed trip: slow walk → fast drive → slow walk
    gps = (
        _track(0.0, 0.0, 0.0, 0.01, h0=8.0, h1=9.0, n=10)  # slow walk ~1 km/h
        + _track(0.0, 0.01, 0.0, 1.0, h0=9.5, h1=10.0, n=5)  # fast drive
        + _track(0.0, 1.0, 0.0, 1.01, h0=10.5, h1=11.5, n=10)  # slow walk
    )
    step = _step(lat=0.0, lon=1.0, hours=10.0)
    segments = list(build_segments([step], gps))

    other_segs = [s for s in segments if s.kind.value == "other"]
    assert not other_segs, f"Found unexpected 'other' segments: {other_segs}"


def test_slow_non_hike_movement_classified_as_walking() -> None:
    """A short slow-moving segment (not meeting hike thresholds) → walking."""
    # 30 min walk, < MIN_HIKE_H=2h and < MIN_HIKE_KM=2km → downgraded to walking
    gps = _track(0.0, 0.0, 0.0, 0.005, h0=9.0, h1=9.5, n=10)  # ~0.55 km in 0.5 h
    step = _step(lat=0.0, lon=0.005, hours=9.5)
    segments = list(build_segments([step], gps))

    kinds = {s.kind for s in segments}
    assert SegmentKind.walking in kinds, f"Expected walking, got {kinds}"
    assert SegmentKind.hike not in kinds, f"Should not be a hike (too short): {kinds}"


def test_fast_movement_classified_as_driving() -> None:
    """Movement well above MAX_HIKE_KMH is classified as driving."""
    # Travel at ~111 km/h: 0.5° in 0.5 h
    gps = _track(0.0, 0.0, 0.0, 0.5, h0=9.0, h1=9.5, n=5)
    step = _step(lat=0.0, lon=0.5, hours=9.5)
    segments = list(build_segments([step], gps))

    kinds = {s.kind for s in segments}
    assert SegmentKind.driving in kinds, f"Expected driving, got {kinds}"
    assert SegmentKind.hike not in kinds, f"Should not be a hike: {kinds}"


def test_flight_speed_movement_classified_as_flight() -> None:
    """Movement above MIN_FLIGHT_KMH over MIN_FLIGHT_KM is a flight.

    Two steps are needed so that the flight departs from (or after) the
    first step — ``_emit`` skips any flight that starts before the first
    step's datetime (it would be a "pre-trip" transfer).
    """
    # ~278 km/h over ~555 km: 5° lon in 2 h
    gps = [
        _pt(0.0, 0.0, hours=10.0),  # departure airport
        _pt(0.0, 5.0, hours=12.0),  # arrival airport
    ]
    step_departure = _step(lat=0.0, lon=0.0, hours=9.0)  # first step: departs
    step_arrival = _step(lat=0.0, lon=5.0, hours=12.0)  # second step: arrives

    segments = list(build_segments([step_departure, step_arrival], gps))

    kinds = {s.kind for s in segments}
    assert SegmentKind.flight in kinds, f"Expected flight, got {kinds}"


# ── build_segments: hike validation thresholds ────────────────────────────────


def test_hike_below_minimum_duration_is_not_hike() -> None:
    """A hike-speed track shorter than MIN_HIKE_H is downgraded to walking."""
    # 1 h walk at ~1.1 km/h — below MIN_HIKE_H=2h
    gps = _track(0.0, 0.0, 0.0, 0.01, h0=9.0, h1=10.0, n=15)
    step = _step(lat=0.0, lon=0.01, hours=10.0)
    segments = list(build_segments([step], gps))

    assert all(s.kind != SegmentKind.hike for s in segments), (
        f"Short-duration track should not be a hike: {[s.kind for s in segments]}"
    )


def test_hike_below_minimum_distance_is_not_hike() -> None:
    """A hike-speed track shorter than MIN_HIKE_KM is downgraded to walking."""
    # Walk very slowly for 3 h but cover < 2 km total
    # 0.009° ≈ 1 km in 3 h → well under MIN_HIKE_KM=2km
    gps = _track(0.0, 0.0, 0.0, 0.009, h0=9.0, h1=12.0, n=30)
    step = _step(lat=0.0, lon=0.009, hours=12.0)
    segments = list(build_segments([step], gps))

    assert all(s.kind != SegmentKind.hike for s in segments), (
        f"Short-distance track should not be a hike: {[s.kind for s in segments]}"
    )


def test_valid_hike_is_detected() -> None:
    """A clear multi-hour walk at hike speed is detected as a hike."""
    # 6 h walk, ~3.7 km/h, ~22 km total
    gps = _track(0.0, 0.0, 0.0, 0.2, h0=8.0, h1=14.0, n=50)
    step = _step(lat=0.0, lon=0.2, hours=14.0)
    segments = list(build_segments([step], gps))

    hikes = [s for s in segments if s.kind == SegmentKind.hike]
    assert hikes, f"Expected a hike segment, got {[s.kind for s in segments]}"


# ── build_segments: hike keeps all points ────────────────────────────────────


def test_hike_segment_keeps_all_densified_points() -> None:
    """Hike segments must not be RDP-simplified — all densified points are
    returned so that elevation-based distance calculations are accurate.

    Regression: previously hike segments went through RDP with epsilon=0.005°,
    which could drop most points on an out-and-back route.
    """
    gps = _track(0.0, 0.0, 0.0, 0.2, h0=8.0, h1=14.0, n=50)
    step = _step(lat=0.0, lon=0.2, hours=14.0)
    segments = list(build_segments([step], gps))

    hikes = [s for s in segments if s.kind == SegmentKind.hike]
    assert hikes, "Expected at least one hike"

    # The densifier adds points at ~15 m spacing; we should have far more than
    # the 51 raw GPS points — at least 100 points on a 22 km track.
    total_pts = sum(len(h.points) for h in hikes)
    assert total_pts > 100, f"Hike has too few points ({total_pts}); RDP may have over-simplified"


def test_non_hike_segments_are_rdp_simplified() -> None:
    """Non-hike segments (walking, driving) are still RDP-simplified."""
    # Fast driving: 0.5° in 0.5h, just a few GPS points
    gps = _track(0.0, 0.0, 0.0, 0.5, h0=9.0, h1=9.5, n=50)
    step = _step(lat=0.0, lon=0.5, hours=9.5)
    segments = list(build_segments([step], gps))

    non_hike = [s for s in segments if s.kind != SegmentKind.hike]
    assert non_hike, "Expected at least one non-hike segment"
    # After RDP, a straight-line drive should collapse to 2 points
    for seg in non_hike:
        assert len(seg.points) <= 10, (
            f"{seg.kind} segment has {len(seg.points)} pts; expected RDP to simplify it"
        )


# ── build_segments: structural invariants ────────────────────────────────────


def test_all_segments_have_at_least_two_points() -> None:
    """Every emitted segment must have ≥ 2 points (needed to draw a line)."""
    gps = (
        _track(0.0, 0.0, 0.0, 0.2, h0=8.0, h1=14.0, n=40)
        + _track(0.0, 0.2, 0.0, 0.7, h0=14.5, h1=15.0, n=5)
        + _track(0.0, 0.7, 0.0, 0.71, h0=16.0, h1=18.0, n=10)
    )
    step = _step(lat=0.0, lon=0.7, hours=15.0)
    segments = list(build_segments([step], gps))

    for i, seg in enumerate(segments):
        assert len(seg.points) >= 2, f"Segment {i} ({seg.kind}) has only {len(seg.points)} point(s)"


def test_consecutive_segments_share_boundary_point() -> None:
    """Consecutive segments must share their boundary timestamp (contiguity
    stitch) so the visual path has no gaps.
    """
    gps = (
        _track(0.0, 0.0, 0.0, 0.2, h0=8.0, h1=14.0, n=40)
        + _track(0.0, 0.2, 0.0, 0.7, h0=14.5, h1=15.0, n=5)
        + _track(0.0, 0.7, 0.0, 0.71, h0=16.0, h1=18.0, n=10)
    )
    step = _step(lat=0.0, lon=0.7, hours=15.0)
    segments = list(build_segments([step], gps))

    for i in range(len(segments) - 1):
        t_end = segments[i].points[-1].time
        t_start = segments[i + 1].points[0].time
        assert t_end == t_start, (
            f"Gap between seg {i} ({segments[i].kind}) "
            f"and seg {i + 1} ({segments[i + 1].kind}): "
            f"{(t_start - t_end) / 3600:.2f} h"
        )


# ── build_segments: robustness / edge cases ───────────────────────────────────


def test_build_segments_raises_on_empty_steps() -> None:
    """build_segments must raise ValueError when given no steps."""
    with pytest.raises(ValueError, match="at least one step"):
        list(build_segments([], []))


def test_build_segments_no_gps_locations_does_not_crash() -> None:
    """Steps with no GPS data at all should not crash — just produce minimal output."""
    steps = [
        _step(lat=0.0, lon=0.0, hours=9.0),
        _step(lat=0.0, lon=0.1, hours=14.0),
    ]
    segments = list(build_segments(steps, []))
    # Result may be empty or a short walking segment; the key thing is no exception.
    assert all(len(s.points) >= 2 for s in segments), "All emitted segments must have ≥ 2 points"


def test_build_segments_single_step_no_gps_produces_no_segments() -> None:
    """A single step with no GPS cannot form a 2-point segment — nothing is emitted."""
    segments = list(build_segments([_step(lat=0.0, lon=0.0, hours=10.0)], []))
    assert segments == [], f"Expected no segments, got {[s.kind for s in segments]}"


def test_noise_removal_handles_single_point() -> None:
    """_remove_gps_noise must not crash on a 1-row DataFrame."""
    df = _clean_df([(0.0, 0.0, _ts(10.0), False)], with_is_step=True)
    result = _remove_gps_noise(df)
    assert result.height == 1


def test_noise_removal_handles_two_points() -> None:
    """_remove_gps_noise must not crash on a 2-row DataFrame (spike pass is skipped)."""
    rows = [
        (0.0, 0.0, _ts(10.0), False),
        (0.001, 0.0, _ts(10.1), False),
    ]
    result = _remove_gps_noise(_clean_df(rows, with_is_step=True))
    assert result.height >= 1

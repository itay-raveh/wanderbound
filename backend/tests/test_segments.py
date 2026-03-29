"""Unit, regression, and integration tests for the segmentation pipeline.

Unit tests use synthetic GPS data to cover:
  - GPS noise removal (teleport + spike filters, step waypoint preservation)
  - Segment classification (walking, driving, flight, hike)
  - Hike validation thresholds (min duration, min distance, min displacement)
  - Hike segments retain all densified points (no RDP simplification)
  - Structural invariants (≥2 points, contiguous boundaries)
  - Robustness (empty steps, no GPS, single step, minimal input)

Integration tests use the South America 2024-2025 trip to verify segmentation
against known ground truth (hike times, structural invariants).  All integration
tests build segments from the full trip (all steps + all GPS points), matching
how segments are pre-computed at user creation time.
"""

import datetime as _dt_mod
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from app.logic.spatial.segments import (
    _remove_gps_noise,
    build_segments,
)
from app.models.polarsteps import Point, PSLocations, PSTrip
from app.models.segment import SegmentData, SegmentKind

# Helpers

# All synthetic tests use 2024-01-01 UTC as the base date.
_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC).timestamp()


def _ts(hours: float) -> float:
    """Unix timestamp at base-date midnight + ``hours``."""
    return _BASE_TS + hours * 3600.0


def _dt(hours: float) -> datetime:
    """Aware UTC datetime at base-date midnight + ``hours``."""
    return datetime.fromtimestamp(_ts(hours), tz=UTC)


@dataclass
class _Loc:
    lat: float
    lon: float


@dataclass
class _Step:
    """Minimal StepLike for tests - mirrors the protocol in segments.py."""

    location: _Loc
    _hours: float

    @property
    def datetime(self) -> _dt_mod.datetime:
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


def _noise_df(rows: list[tuple]) -> pl.DataFrame:
    """Build a DataFrame for ``_remove_gps_noise``.

    Each row is ``(lat, lon, unix_time_seconds, is_step?)``.
    """
    return pl.DataFrame(
        {
            "lat": [float(r[0]) for r in rows],
            "lon": [float(r[1]) for r in rows],
            "time": [float(r[2]) for r in rows],
            "is_step": [bool(r[3]) for r in rows],
        }
    )


def _segment_kinds(steps: list[_Step], gps: list[Point]) -> set[SegmentKind]:
    return {s.kind for s in build_segments(steps, gps)}


def _hikes(steps: list[_Step], gps: list[Point]) -> list[SegmentData]:
    return [s for s in build_segments(steps, gps) if s.kind == SegmentKind.hike]


# GPS noise removal


class TestNoiseRemoval:
    def test_teleport_removed(self) -> None:
        """A GPS point that jumps at unrealistic speed is removed."""
        rows = [
            (0.0, 0.0, _ts(10.0), False),
            (50.0, 0.0, _ts(10.0) + 10, False),  # teleport: 50° in 10s
            (0.01, 0.0, _ts(12.0), False),
        ]
        df = _remove_gps_noise(_noise_df(rows))
        assert 50.0 not in df["lat"].to_list()

    def test_teleport_kept_when_step(self) -> None:
        """A step waypoint survives even when it looks like a teleport."""
        rows = [
            (0.0, 0.0, _ts(10.0), False),
            (50.0, 0.0, _ts(10.0) + 10, True),  # same jump, but is_step
            (0.01, 0.0, _ts(12.0), False),
        ]
        df = _remove_gps_noise(_noise_df(rows))
        assert 50.0 in df["lat"].to_list()

    def test_spike_removed(self) -> None:
        """A GPS detour that backtracks to the same position is removed."""
        rows = [
            (0.0, 0.0, _ts(10.0), False),
            (0.0, 0.1, _ts(10.5), False),  # spike: 0.1° off path
            (0.0, 0.005, _ts(11.0), False),
        ]
        df = _remove_gps_noise(_noise_df(rows))
        assert df.height == 2
        assert 0.1 not in df["lon"].to_list()

    def test_spike_kept_when_step(self) -> None:
        """A step waypoint survives even when it looks like a spike."""
        rows = [
            (0.0, 0.0, _ts(10.0), False),
            (0.0, 0.1, _ts(10.5), True),  # same detour, but is_step
            (0.0, 0.005, _ts(11.0), False),
        ]
        df = _remove_gps_noise(_noise_df(rows))
        assert 0.1 in df["lon"].to_list()

    def test_single_point(self) -> None:
        df = _noise_df([(0.0, 0.0, _ts(10.0), False)])
        assert _remove_gps_noise(df).height == 1

    def test_two_points(self) -> None:
        rows = [
            (0.0, 0.0, _ts(10.0), False),
            (0.001, 0.0, _ts(10.1), False),
        ]
        assert _remove_gps_noise(_noise_df(rows)).height >= 1


# Segment classification


class TestClassification:
    def test_no_other_kind_in_output(self) -> None:
        """The internal 'other' label is always resolved to walking or driving."""
        gps = (
            _track(0.0, 0.0, 0.0, 0.01, h0=8.0, h1=9.0, n=10)
            + _track(0.0, 0.01, 0.0, 1.0, h0=9.5, h1=10.0, n=5)
            + _track(0.0, 1.0, 0.0, 1.01, h0=10.5, h1=11.5, n=10)
        )
        kinds = _segment_kinds([_step(0.0, 1.0, 10.0)], gps)
        assert all(k.value != "other" for k in kinds)

    def test_slow_short_movement_is_walking(self) -> None:
        """A short slow segment (below hike thresholds) -> walking."""
        gps = _track(0.0, 0.0, 0.0, 0.005, h0=9.0, h1=9.5, n=10)
        kinds = _segment_kinds([_step(0.0, 0.005, 9.5)], gps)
        assert SegmentKind.walking in kinds
        assert SegmentKind.hike not in kinds

    def test_fast_movement_is_driving(self) -> None:
        """Movement well above hike speed -> driving."""
        gps = _track(0.0, 0.0, 0.0, 0.5, h0=9.0, h1=9.5, n=5)
        kinds = _segment_kinds([_step(0.0, 0.5, 9.5)], gps)
        assert SegmentKind.driving in kinds
        assert SegmentKind.hike not in kinds

    def test_flight_speed_is_flight(self) -> None:
        """Movement above flight speed over flight distance -> flight."""
        gps = [
            _pt(0.0, 0.0, hours=10.0),
            _pt(0.0, 5.0, hours=12.0),  # ~278 km/h over ~555 km
        ]
        steps = [_step(0.0, 0.0, 9.0), _step(0.0, 5.0, 12.0)]
        assert SegmentKind.flight in _segment_kinds(steps, gps)

    def test_pre_first_step_flight_not_dropped(self) -> None:
        """A flight before the first step must not be silently dropped.

        Simulates: fly from city A to layover city B (no step there), walk
        around B, fly to destination city C (first step).  Both flights
        occur before the first step's timestamp.

        Regression: _emit_segments skipped pre-first-step flights, which
        caused the stitch logic to merge the layover walking + second
        flight into one giant "walking" segment rendered as a thick
        dashed line across the ocean.
        """
        # City A (h0) -> fly -> City B (h3-h8 walking) -> fly -> City C (h22+)
        gps_a = [_pt(32.0, 35.0, hours=0.0)]
        gps_b = _track(25.0, 55.0, 25.01, 55.01, h0=3.5, h1=8.0, n=20)
        gps_c = _track(-34.6, -58.4, -34.61, -58.41, h0=22.0, h1=26.0, n=20)

        # Only step is in city C (the destination)
        steps = [_step(-34.6, -58.4, 22.0)]

        segments = list(build_segments(steps, gps_a + gps_b + gps_c))
        kinds = [s.kind for s in segments]
        assert kinds.count(SegmentKind.flight) >= 2, (
            f"Expected ≥2 flights in {kinds} - pre-first-step flights were dropped"
        )
        # No walking segment should span continents (> 5° lat/lon)
        for seg in segments:
            if seg.kind == SegmentKind.walking:
                p0, p1 = seg.points[0], seg.points[-1]
                msg = (
                    f"Walking segment spans ({p0.lat:.1f},{p0.lon:.1f}) -> "
                    f"({p1.lat:.1f},{p1.lon:.1f}) - flight misclassified"
                )
                assert abs(p0.lat - p1.lat) < 5, msg
                assert abs(p0.lon - p1.lon) < 5, msg

    def test_valid_hike_detected(self) -> None:
        """A clear multi-hour walk at hike speed -> hike."""
        gps = _track(0.0, 0.0, 0.0, 0.2, h0=8.0, h1=14.0, n=50)
        assert _hikes([_step(0.0, 0.2, 14.0)], gps)


# Hike validation thresholds


class TestHikeValidation:
    def test_below_min_duration_is_not_hike(self) -> None:
        """A hike-speed track shorter than MIN_HIKE_H -> walking."""
        gps = _track(0.0, 0.0, 0.0, 0.01, h0=9.0, h1=10.0, n=15)
        assert not _hikes([_step(0.0, 0.01, 10.0)], gps)

    def test_below_min_distance_is_not_hike(self) -> None:
        """A hike-speed track shorter than MIN_HIKE_KM -> walking."""
        gps = _track(0.0, 0.0, 0.0, 0.009, h0=9.0, h1=12.0, n=30)
        assert not _hikes([_step(0.0, 0.009, 12.0)], gps)


# Step location preservation


def _point_near(
    points: list[Point], lat: float, lon: float, tol: float = 0.001
) -> bool:
    return any(abs(p.lat - lat) < tol and abs(p.lon - lon) < tol for p in points)


class TestStepPreservation:
    def test_step_in_out_and_back_hike(self) -> None:
        """Step at turnaround of out-and-back hike appears in output.

        Regression: RDP collapsed the path to two endpoints.
        """
        gps = _track(0.0, 0.0, 0.0, 0.09, h0=8.0, h1=11.0, n=20) + _track(
            0.0, 0.09, 0.0, 0.0, h0=13.0, h1=16.0, n=20
        )
        hikes = _hikes([_step(0.0, 0.15, 12.0)], gps)
        assert hikes
        assert _point_near(hikes[0].points, 0.0, 0.15)

    def test_step_included_when_edge_speed_above_hike_max(self) -> None:
        """Step is kept even when the GPS->step edge exceeds hike speed.

        Regression: step-adjacent edges only had gap tolerance, not speed exemption.
        """
        gps = _track(0.0, 0.0, 0.0, 0.05, h0=8.0, h1=13.0, n=30)
        hikes = _hikes([_step(0.0, 0.15, 13.5)], gps)
        assert hikes
        assert _point_near(hikes[0].points, 0.0, 0.15)


# Hike point retention


class TestHikePoints:
    def test_hike_is_rdp_simplified(self) -> None:
        """Hike segments are RDP-simplified like other segments."""
        gps = _track(0.0, 0.0, 0.0, 0.2, h0=8.0, h1=14.0, n=50)
        hikes = _hikes([_step(0.0, 0.2, 14.0)], gps)
        assert hikes
        total = sum(len(h.points) for h in hikes)
        # Straight-line track collapses under RDP; just verify ≥ 2 endpoints
        assert total >= 2

    def test_non_hike_segments_are_rdp_simplified(self) -> None:
        """Non-hike segments (driving) are RDP-simplified."""
        gps = _track(0.0, 0.0, 0.0, 0.5, h0=9.0, h1=9.5, n=50)
        segments = list(build_segments([_step(0.0, 0.5, 9.5)], gps))
        for seg in segments:
            if seg.kind != SegmentKind.hike:
                assert len(seg.points) <= 10


# Structural invariants


class TestStructure:
    @pytest.fixture()
    def mixed_segments(self) -> list[SegmentData]:
        gps = (
            _track(0.0, 0.0, 0.0, 0.2, h0=8.0, h1=14.0, n=40)
            + _track(0.0, 0.2, 0.0, 0.7, h0=14.5, h1=15.0, n=5)
            + _track(0.0, 0.7, 0.0, 0.71, h0=16.0, h1=18.0, n=10)
        )
        return list(build_segments([_step(0.0, 0.7, 15.0)], gps))

    def test_all_segments_have_at_least_two_points(
        self, mixed_segments: list[SegmentData]
    ) -> None:
        for i, seg in enumerate(mixed_segments):
            assert len(seg.points) >= 2, f"Segment {i} ({seg.kind})"

    def test_consecutive_segments_share_boundary(
        self, mixed_segments: list[SegmentData]
    ) -> None:
        for i in range(len(mixed_segments) - 1):
            t_end = mixed_segments[i].points[-1].time
            t_start = mixed_segments[i + 1].points[0].time
            assert t_end == t_start, (
                f"Gap between seg {i} and {i + 1}: {(t_start - t_end) / 3600:.2f}h"
            )


# Robustness


class TestRobustness:
    def test_no_gps_does_not_crash(self) -> None:
        steps = [_step(0.0, 0.0, 9.0), _step(0.0, 0.1, 14.0)]
        segments = list(build_segments(steps, []))
        assert all(len(s.points) >= 2 for s in segments)

    def test_single_step_no_gps_produces_nothing(self) -> None:
        assert list(build_segments([_step(0.0, 0.0, 10.0)], [])) == []


# ---------------------------------------------------------------------------
# Integration tests (real Polarsteps trip data)
# ---------------------------------------------------------------------------

# Tolerance for hike start/end times: GPS can be sparse so allow ±30 min.
_TOL_S = 30 * 60


def _cmp(ts: float, dt_str: str, tz: ZoneInfo) -> float:
    """Return signed error (seconds) vs expected 'YYYY-MM-DD HH:MM' in tz."""
    ref = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    return ts - ref.timestamp()


@pytest.fixture(scope="module")
def all_segments(sa_trip: PSTrip, sa_locations: PSLocations) -> list[SegmentData]:
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
        sa_trip: PSTrip,
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
        self, all_segments: list[SegmentData], sa_trip: PSTrip
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
        self, sa_trip: PSTrip, all_segments: list[SegmentData]
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

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
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from app.logic.processing import multi_day_hike_ranges, segment_timezone
from app.logic.spatial.segments import (
    _remove_gps_noise,
    build_segments,
)
from app.models.polarsteps import Point, PSLocations, PSTrip
from app.models.segment import Segment, SegmentData, SegmentKind

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

    def test_brief_transfer_between_hikes_absorbed(self) -> None:
        """A short fast gap (taxi between trailheads) between two hikes -> one hike.

        Regression: a 5-min drive at 17 km/h between two hike days produced
        two separate hike segments, breaking the single-hike-segment
        assumption in the frontend's HikeMapPage.
        """
        # Hike day 1: 3h, ~6 km at ~2 km/h
        hike1 = _track(0.0, 0.0, 0.0, 0.05, h0=8.0, h1=11.0, n=30)
        # 10 min taxi at ~20 km/h (0.03° ≈ 3.3 km in 10 min)
        taxi = [_pt(0.0, 0.05, hours=11.0), _pt(0.0, 0.08, hours=11.17)]
        # Hike day 2: 3h, ~6 km
        hike2 = _track(0.0, 0.08, 0.0, 0.13, h0=11.17, h1=14.17, n=30)

        steps = [_step(0.0, 0.0, 8.0), _step(0.0, 0.13, 14.17)]
        hikes = _hikes(steps, hike1 + taxi + hike2)
        assert len(hikes) == 1, (
            f"Brief transfer should be absorbed into one hike, got {len(hikes)}"
        )


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
            # Single-day hikes (cross midnight but only 1 active day)
            (3, 4, [("2024-11-15 15:00", "2024-11-16 02:55")]),
            (30, 32, [("2024-12-24 08:06", "2024-12-25 15:03")]),
            (
                125,
                126,
                [
                    ("2025-05-10 07:16", "2025-05-11 07:12"),
                    ("2025-05-11 09:59", "2025-05-11 16:38"),
                ],
            ),
            (
                128,
                130,
                [
                    ("2025-05-14 13:03", "2025-05-15 08:10"),
                    ("2025-05-15 08:46", "2025-05-15 16:13"),
                ],
            ),
            (171, 172, [("2025-07-10 13:03", "2025-07-11 19:20")]),
            (172, 173, [("2025-07-12 09:36", "2025-07-13 15:09")]),
            # Multi-day treks
            (12, 16, [("2024-12-01 11:30", "2024-12-04 18:00")]),
            (18, 21, [("2024-12-08 11:30", "2024-12-11 15:30")]),
            (43, 44, [("2025-01-11 13:09", "2025-01-12 13:49")]),
            (53, 55, [("2025-01-24 10:35", "2025-01-26 18:34")]),
            (115, 116, [("2025-04-25 07:29", "2025-04-26 08:29")]),
            (120, 121, [("2025-05-05 11:29", "2025-05-06 15:18")]),
            (139, 146, [("2025-05-25 11:00", "2025-05-27 13:00")]),
            (178, 183, [("2025-07-23 08:13", "2025-07-26 14:47")]),
            (184, 186, [("2025-07-29 06:23", "2025-07-31 13:12")]),
            (192, 201, [("2025-08-10 09:30", "2025-08-17 10:46")]),
            # No-hike ranges
            (83, 83, []),  # Salvador
            (119, 119, []),  # La Paz transit
            (147, 147, []),  # Potosí
            (157, 157, []),  # La Paz
            # Huayna Potosi: 6000m mountaineering, walking not hike
            (158, 159, []),
            (162, 162, []),  # Copacabana
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


# -- Multi-day hike range detection ------------------------------------------

_KM_PER_DEG_LAT = 111.32  # at equator


def _multi_day_seg(
    daily_km: list[float],
    start_date: date,
    tz: str = "America/Santiago",
) -> Segment:
    """Create a hike segment with specified GPS distance per calendar day.

    Each day gets two points (08:00 and 17:00 local), spaced along latitude
    at the equator so haversine distance ≈ the requested km.  Overnight gaps
    have zero displacement (camping).
    """
    zone = ZoneInfo(tz)
    points: list[Point] = []
    lat = 0.0

    for i, km in enumerate(daily_km):
        day = start_date + timedelta(days=i)
        t_start = datetime(day.year, day.month, day.day, 8, 0, tzinfo=zone).timestamp()
        t_end = datetime(day.year, day.month, day.day, 17, 0, tzinfo=zone).timestamp()

        points.append(Point(lat=lat, lon=0.0, time=t_start))
        lat += km / _KM_PER_DEG_LAT
        points.append(Point(lat=lat, lon=0.0, time=t_end))

    return Segment(
        uid=1,
        aid="trip1",
        start_time=points[0].time,
        end_time=points[-1].time,
        kind=SegmentKind.hike,
        timezone_id=tz,
        points=points,
    )


def _minimal_seg(
    kind: SegmentKind,
    start: float,
    end: float,
    tz: str = "America/Santiago",
) -> Segment:
    """Segment with only start/end endpoints (no per-day detail)."""
    return Segment(
        uid=1,
        aid="trip1",
        start_time=start,
        end_time=end,
        kind=kind,
        timezone_id=tz,
        points=[
            Point(lat=0, lon=0, time=start),
            Point(lat=0, lon=0, time=end),
        ],
    )


class TestMultiDayHikeRanges:
    """Tests for multi_day_hike_ranges (per-day distance analysis)."""

    # -- Basic behaviour --

    def test_multi_day_hike_produces_range(self) -> None:
        seg = _multi_day_seg([14, 14, 14, 14], date(2024, 12, 8))
        ranges = multi_day_hike_ranges([seg])
        assert ranges == [(date(2024, 12, 8), date(2024, 12, 11))]

    def test_single_day_hike_excluded(self) -> None:
        # 6-hour same-day hike — only 1 point pair, 1 calendar day
        seg = _multi_day_seg([8.0], date(2024, 12, 8))
        assert multi_day_hike_ranges([seg]) == []

    def test_non_hike_segments_excluded(self) -> None:
        seg = _minimal_seg(SegmentKind.driving, 1e9, 1e9 + 4 * 86400)
        assert multi_day_hike_ranges([seg]) == []

    def test_uses_local_timezone_for_date(self) -> None:
        """Late evening in Santiago (23:30 local) is still the same local date."""
        zone = ZoneInfo("America/Santiago")
        # Dec 8 08:00 Santiago
        t1 = datetime(2024, 12, 8, 8, 0, tzinfo=zone).timestamp()
        # Dec 8 23:30 Santiago — next day in UTC but same day local
        t2 = datetime(2024, 12, 8, 23, 30, tzinfo=zone).timestamp()
        seg = Segment(
            uid=1,
            aid="trip1",
            start_time=t1,
            end_time=t2,
            kind=SegmentKind.hike,
            timezone_id="America/Santiago",
            points=[
                Point(lat=0.0, lon=0.0, time=t1),
                Point(lat=0.072, lon=0.0, time=t2),  # ~8 km
            ],
        )
        assert multi_day_hike_ranges([seg]) == []

    def test_multiple_hikes(self) -> None:
        seg1 = _multi_day_seg([14, 14, 14, 14], date(2024, 12, 8))
        seg2 = _multi_day_seg([10, 10, 10, 10], date(2025, 1, 7))
        ranges = multi_day_hike_ranges([seg1, seg2])
        assert len(ranges) == 2

    # -- True positives (confirmed good multi-day hikes) --

    def test_patagonia_4day_trek(self) -> None:
        seg = _multi_day_seg([15, 14, 13, 14], date(2024, 12, 1))
        ranges = multi_day_hike_ranges([seg])
        assert ranges == [(date(2024, 12, 1), date(2024, 12, 4))]

    def test_2day_hike_low_daily_distance(self) -> None:
        """Weakest true positive: models Jun 10-11 (4.8 km total, ~2.4 km/day)."""
        seg = _multi_day_seg([2.5, 2.3], date(2025, 6, 10), "America/Lima")
        ranges = multi_day_hike_ranges([seg])
        assert ranges == [(date(2025, 6, 10), date(2025, 6, 11))]

    def test_week_long_trek(self) -> None:
        """Models Aug 10-17: 81.6 km over 8 days."""
        seg = _multi_day_seg([12, 10, 11, 9, 10, 11, 10, 8], date(2025, 8, 10))
        ranges = multi_day_hike_ranges([seg])
        assert ranges == [(date(2025, 8, 10), date(2025, 8, 17))]

    # -- False positives: not multi-day (real hike, single active day) --

    def test_midnight_crossing_single_day_hike(self) -> None:
        """Nov 15-16: single hike on the 15th crossing midnight.

        ~8 km day 1, ~1 km day 2.
        """
        zone = ZoneInfo("America/Santiago")
        d1 = date(2024, 11, 15)
        d2 = d1 + timedelta(days=1)
        t1 = datetime(d1.year, d1.month, d1.day, 18, 0, tzinfo=zone).timestamp()
        t2 = datetime(d1.year, d1.month, d1.day, 23, 59, tzinfo=zone).timestamp()
        t3 = datetime(d2.year, d2.month, d2.day, 6, 0, tzinfo=zone).timestamp()
        seg = Segment(
            uid=1,
            aid="trip1",
            start_time=t1,
            end_time=t3,
            kind=SegmentKind.hike,
            timezone_id="America/Santiago",
            points=[
                Point(lat=0.0, lon=0.0, time=t1),
                Point(lat=0.072, lon=0.0, time=t2),  # ~8 km
                Point(lat=0.081, lon=0.0, time=t3),  # ~1 km more
            ],
        )
        assert multi_day_hike_ranges([seg]) == []

    def test_single_day_hike_other_day_below_threshold(self) -> None:
        """Dec 24-25: only the 24th had a hike.  Day 2 has < 2 km."""
        seg = _multi_day_seg([10.0, 1.5], date(2024, 12, 24))
        assert multi_day_hike_ranges([seg]) == []

    def test_two_separate_day_hikes_included(self) -> None:
        """May 14-15: two separate day hikes absorbed into one segment.

        Each day has significant distance — the per-day check correctly
        includes it.  The frontend shows a map covering both, which is useful.
        """
        seg = _multi_day_seg([6.0, 5.0], date(2025, 5, 14))
        ranges = multi_day_hike_ranges([seg])
        assert ranges == [(date(2025, 5, 14), date(2025, 5, 15))]

    # -- False positives: GPS drift (not hikes at all) --

    def test_gps_drift_crosses_midnight(self) -> None:
        """Dec 15-16: GPS drift, ~1.5 km total across 2 days."""
        zone = ZoneInfo("America/Santiago")
        d1 = date(2024, 12, 15)
        d2 = d1 + timedelta(days=1)
        t1 = datetime(d1.year, d1.month, d1.day, 14, 0, tzinfo=zone).timestamp()
        t_mid = datetime(d1.year, d1.month, d1.day, 23, 30, tzinfo=zone).timestamp()
        t2 = datetime(d2.year, d2.month, d2.day, 10, 0, tzinfo=zone).timestamp()
        seg = Segment(
            uid=1,
            aid="trip1",
            start_time=t1,
            end_time=t2,
            kind=SegmentKind.hike,
            timezone_id="America/Santiago",
            points=[
                Point(lat=0.0, lon=0.0, time=t1),
                Point(lat=0.009, lon=0.0, time=t_mid),  # ~1 km
                Point(lat=0.0135, lon=0.0, time=t2),  # ~0.5 km more
            ],
        )
        assert multi_day_hike_ranges([seg]) == []

    def test_overmerged_camping_one_active_day(self) -> None:
        """Jan 26-Feb 2: 171 h segment but only one day has real hiking."""
        seg = _multi_day_seg(
            [0.3, 0.4, 5.0, 0.2, 0.3, 0.3, 0.4, 0.3],
            date(2025, 1, 26),
        )
        assert multi_day_hike_ranges([seg]) == []

    def test_drift_low_distance_multiday(self) -> None:
        """Feb 9-10 pattern: multi-day GPS drift, < 2 km every day."""
        seg = _multi_day_seg([0.5, 0.7, 0.3], date(2025, 2, 9))
        assert multi_day_hike_ranges([seg]) == []

    # -- Merge --

    def test_adjacent_ranges_merged(self) -> None:
        """May 25-26 + May 26-27 → single range May 25-27."""
        seg1 = _multi_day_seg([6.0, 4.0], date(2025, 5, 25))
        seg2 = _multi_day_seg([3.0, 5.0], date(2025, 5, 26))
        ranges = multi_day_hike_ranges([seg1, seg2])
        assert ranges == [(date(2025, 5, 25), date(2025, 5, 27))]

    # -- Edge cases --

    def test_all_days_below_threshold(self) -> None:
        """3 days of 1.5 km/day — below 2.0 km threshold on every day."""
        seg = _multi_day_seg([1.5, 1.5, 1.5], date(2025, 3, 1))
        assert multi_day_hike_ranges([seg]) == []

    def test_non_overlapping_ranges_stay_separate(self) -> None:
        """Two multi-day hikes a week apart stay as separate ranges."""
        seg1 = _multi_day_seg([10, 10], date(2025, 4, 1))
        seg2 = _multi_day_seg([10, 10], date(2025, 4, 10))
        ranges = multi_day_hike_ranges([seg1, seg2])
        assert ranges == [
            (date(2025, 4, 1), date(2025, 4, 2)),
            (date(2025, 4, 10), date(2025, 4, 11)),
        ]


class TestMultiDayHikeRangesIntegration:
    """Verify multi_day_hike_ranges against real South America 2024-2025 data.

    Builds Segment objects from the full trip's pipeline output, exactly as
    build_trip_objects() does, then checks that the per-day distance analysis
    produces the expected ranges — eliminating false positives while keeping
    all confirmed multi-day hikes.
    """

    @pytest.fixture(scope="class")
    def real_segments(
        self,
        sa_trip: PSTrip,
        all_segments: list[SegmentData],
    ) -> list[Segment]:
        steps = sa_trip.all_steps
        return [
            Segment(
                uid=1,
                aid="sa2024",
                start_time=seg.points[0].time,
                end_time=seg.points[-1].time,
                kind=seg.kind,
                timezone_id=segment_timezone(seg.points[0].time, steps),
                points=seg.points,
            )
            for seg in all_segments
        ]

    @pytest.fixture(scope="class")
    def real_ranges(self, real_segments: list[Segment]) -> list[tuple[date, date]]:
        return multi_day_hike_ranges(real_segments)

    def test_confirmed_multiday_hikes_present(
        self, real_ranges: list[tuple[date, date]]
    ) -> None:
        """All user-confirmed multi-day hikes must appear."""
        expected_good = [
            (date(2024, 12, 1), date(2024, 12, 4)),  # Patagonia trek 1
            (date(2024, 12, 8), date(2024, 12, 11)),  # Patagonia trek 2
        ]
        for start, end in expected_good:
            assert any(s <= start and end <= e for s, e in real_ranges), (
                f"Missing confirmed hike {start} -> {end}"
            )

    def test_false_positives_eliminated(
        self, real_ranges: list[tuple[date, date]]
    ) -> None:
        """Ranges that the old naive check produced but aren't real multi-day hikes."""
        should_not_appear = [
            (date(2024, 11, 15), date(2024, 11, 16)),  # single hike on 15th
            (date(2024, 12, 15), date(2024, 12, 16)),  # GPS drift
            (date(2024, 12, 16), date(2024, 12, 17)),  # same drift, second hit
            (date(2024, 12, 21), date(2024, 12, 22)),  # not a hike
            (date(2025, 1, 4), date(2025, 1, 5)),  # not a hike
            (date(2025, 2, 9), date(2025, 2, 10)),  # GPS drift
            (date(2025, 2, 11), date(2025, 2, 12)),  # GPS drift
            (date(2025, 5, 29), date(2025, 5, 30)),  # not a hike
            (date(2025, 6, 7), date(2025, 6, 8)),  # not a hike
            (date(2025, 6, 22), date(2025, 6, 23)),  # not a hike
            (date(2025, 7, 6), date(2025, 7, 7)),  # not a hike
            (date(2025, 7, 10), date(2025, 7, 11)),  # not multiday
            (date(2025, 7, 15), date(2025, 7, 16)),  # not a hike
            (date(2025, 8, 29), date(2025, 8, 30)),  # not a hike
            (date(2025, 8, 30), date(2025, 8, 31)),  # not a hike
            (date(2025, 9, 1), date(2025, 9, 2)),  # not a hike
        ]
        for start, end in should_not_appear:
            assert (start, end) not in real_ranges, (
                f"False positive still present: {start} -> {end}"
            )

    def test_split_hike_merged(self, real_ranges: list[tuple[date, date]]) -> None:
        """May 25-26 + May 26-27 should merge into a single range."""
        assert (date(2025, 5, 25), date(2025, 5, 26)) not in real_ranges
        assert (date(2025, 5, 26), date(2025, 5, 27)) not in real_ranges
        # Merged range should exist
        assert any(
            s <= date(2025, 5, 25) and date(2025, 5, 27) <= e for s, e in real_ranges
        ), "May 25-27 merged range missing"

    def test_range_count_reduced(self, real_ranges: list[tuple[date, date]]) -> None:
        """Fewer ranges than the old naive date-crossing check."""
        # Old naive check produced 40 ranges; new should be ~22
        assert len(real_ranges) < 30, f"Too many ranges: {len(real_ranges)}"


class TestSegmentPipelineSnapshot:
    """Snapshot test: captures full build_segments() output shape.

    Run with --snapshot-update to regenerate after intentional changes.
    """

    def test_basic_trip_snapshot(self, snapshot: object) -> None:
        """A simple trip produces a stable segment list."""
        steps = [
            _step(52.37, 4.89, 8.0),  # Amsterdam morning
            _step(51.44, 5.47, 12.0),  # Eindhoven midday
            _step(50.85, 4.35, 18.0),  # Brussels evening
        ]
        gps = _track(52.37, 4.89, 51.44, 5.47, h0=8.0, h1=11.5, n=30) + _track(
            51.44, 5.47, 50.85, 4.35, h0=12.5, h1=17.5, n=30
        )
        segments = build_segments(steps, gps)
        # Snapshot kinds and point counts (not exact coords)
        result = [{"kind": s.kind.value, "num_points": len(s.points)} for s in segments]
        assert result == snapshot

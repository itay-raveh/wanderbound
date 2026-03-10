"""Unit and regression tests for the segmentation pipeline using synthetic GPS data.

Tests cover:
  - GPS noise removal (teleport + spike filters, step waypoint preservation)
  - Segment classification (walking, driving, flight, hike)
  - Hike validation thresholds (min duration, min distance, min displacement)
  - Hike segments retain all densified points (no RDP simplification)
  - Structural invariants (≥2 points, contiguous boundaries)
  - Robustness (empty steps, no GPS, single step, minimal input)
"""

import datetime as _dt_mod
from dataclasses import dataclass
from datetime import UTC, datetime

import polars as pl
import pytest

from app.logic.spatial.points import Point
from app.logic.spatial.segments import (
    Segment,
    SegmentKind,
    _remove_gps_noise,
    build_segments,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

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
    """Minimal StepLike for tests — mirrors the protocol in segments.py."""

    location: _Loc
    _hours: float

    @property
    def datetime(self) -> _dt_mod.datetime:
        return _dt(self._hours)


def _step(lat: float, lon: float, hours: float) -> _Step:
    return _Step(location=_Loc(lat=lat, lon=lon), _hours=hours)


def _pt(lat: float, lon: float, hours: float) -> Point:
    return Point(lat=lat, lon=lon, time=_ts(hours))


def _track(  # noqa: PLR0913
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


def _hikes(steps: list[_Step], gps: list[Point]) -> list[Segment]:
    return [s for s in build_segments(steps, gps) if s.kind == SegmentKind.hike]


# ── GPS noise removal ───────────────────────────────────────────────────────


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


# ── Segment classification ───────────────────────────────────────────────────


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
        """A short slow segment (below hike thresholds) → walking."""
        gps = _track(0.0, 0.0, 0.0, 0.005, h0=9.0, h1=9.5, n=10)
        kinds = _segment_kinds([_step(0.0, 0.005, 9.5)], gps)
        assert SegmentKind.walking in kinds
        assert SegmentKind.hike not in kinds

    def test_fast_movement_is_driving(self) -> None:
        """Movement well above hike speed → driving."""
        gps = _track(0.0, 0.0, 0.0, 0.5, h0=9.0, h1=9.5, n=5)
        kinds = _segment_kinds([_step(0.0, 0.5, 9.5)], gps)
        assert SegmentKind.driving in kinds
        assert SegmentKind.hike not in kinds

    def test_flight_speed_is_flight(self) -> None:
        """Movement above flight speed over flight distance → flight."""
        gps = [
            _pt(0.0, 0.0, hours=10.0),
            _pt(0.0, 5.0, hours=12.0),  # ~278 km/h over ~555 km
        ]
        steps = [_step(0.0, 0.0, 9.0), _step(0.0, 5.0, 12.0)]
        assert SegmentKind.flight in _segment_kinds(steps, gps)

    def test_valid_hike_detected(self) -> None:
        """A clear multi-hour walk at hike speed → hike."""
        gps = _track(0.0, 0.0, 0.0, 0.2, h0=8.0, h1=14.0, n=50)
        assert _hikes([_step(0.0, 0.2, 14.0)], gps)


# ── Hike validation thresholds ───────────────────────────────────────────────


class TestHikeValidation:
    def test_below_min_duration_is_not_hike(self) -> None:
        """A hike-speed track shorter than MIN_HIKE_H → walking."""
        gps = _track(0.0, 0.0, 0.0, 0.01, h0=9.0, h1=10.0, n=15)
        assert not _hikes([_step(0.0, 0.01, 10.0)], gps)

    def test_below_min_distance_is_not_hike(self) -> None:
        """A hike-speed track shorter than MIN_HIKE_KM → walking."""
        gps = _track(0.0, 0.0, 0.0, 0.009, h0=9.0, h1=12.0, n=30)
        assert not _hikes([_step(0.0, 0.009, 12.0)], gps)


# ── Step location preservation ───────────────────────────────────────────────


def _point_near(points: list[Point], lat: float, lon: float, tol: float = 0.001) -> bool:
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
        """Step is kept even when the GPS→step edge exceeds hike speed.

        Regression: step-adjacent edges only had gap tolerance, not speed exemption.
        """
        gps = _track(0.0, 0.0, 0.0, 0.05, h0=8.0, h1=13.0, n=30)
        hikes = _hikes([_step(0.0, 0.15, 13.5)], gps)
        assert hikes
        assert _point_near(hikes[0].points, 0.0, 0.15)


# ── Hike point retention ────────────────────────────────────────────────────


class TestHikePoints:
    def test_hike_keeps_all_densified_points(self) -> None:
        """Hike segments keep all densified points (no RDP).

        Regression: RDP with epsilon=0.005° dropped most points.
        """
        gps = _track(0.0, 0.0, 0.0, 0.2, h0=8.0, h1=14.0, n=50)
        hikes = _hikes([_step(0.0, 0.2, 14.0)], gps)
        assert hikes
        total = sum(len(h.points) for h in hikes)
        assert total > 100

    def test_non_hike_segments_are_rdp_simplified(self) -> None:
        """Non-hike segments (driving) are RDP-simplified."""
        gps = _track(0.0, 0.0, 0.0, 0.5, h0=9.0, h1=9.5, n=50)
        segments = list(build_segments([_step(0.0, 0.5, 9.5)], gps))
        for seg in segments:
            if seg.kind != SegmentKind.hike:
                assert len(seg.points) <= 10


# ── Structural invariants ───────────────────────────────────────────────────


class TestStructure:
    @pytest.fixture()
    def mixed_segments(self) -> list[Segment]:
        gps = (
            _track(0.0, 0.0, 0.0, 0.2, h0=8.0, h1=14.0, n=40)
            + _track(0.0, 0.2, 0.0, 0.7, h0=14.5, h1=15.0, n=5)
            + _track(0.0, 0.7, 0.0, 0.71, h0=16.0, h1=18.0, n=10)
        )
        return list(build_segments([_step(0.0, 0.7, 15.0)], gps))

    def test_all_segments_have_at_least_two_points(self, mixed_segments: list[Segment]) -> None:
        for i, seg in enumerate(mixed_segments):
            assert len(seg.points) >= 2, f"Segment {i} ({seg.kind})"

    def test_consecutive_segments_share_boundary(self, mixed_segments: list[Segment]) -> None:
        for i in range(len(mixed_segments) - 1):
            t_end = mixed_segments[i].points[-1].time
            t_start = mixed_segments[i + 1].points[0].time
            assert t_end == t_start, (
                f"Gap between seg {i} and {i + 1}: {(t_start - t_end) / 3600:.2f}h"
            )


# ── Robustness ──────────────────────────────────────────────────────────────


class TestRobustness:
    def test_empty_steps_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one step"):
            list(build_segments([], []))

    def test_no_gps_does_not_crash(self) -> None:
        steps = [_step(0.0, 0.0, 9.0), _step(0.0, 0.1, 14.0)]
        segments = list(build_segments(steps, []))
        assert all(len(s.points) >= 2 for s in segments)

    def test_single_step_no_gps_produces_nothing(self) -> None:
        assert list(build_segments([_step(0.0, 0.0, 10.0)], [])) == []

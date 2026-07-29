import datetime as _dt_mod
from dataclasses import dataclass
from datetime import UTC, datetime

import polars as pl
import pytest

from app.logic.spatial.segments import (
    _remove_gps_noise,
    build_segments,
)
from app.models.polarsteps import Point
from app.models.segment import SegmentData, SegmentKind

_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC).timestamp()


def _ts(hours: float) -> float:
    return _BASE_TS + hours * 3600.0


def _dt(hours: float) -> datetime:
    return datetime.fromtimestamp(_ts(hours), tz=UTC)


@dataclass
class _Loc:
    lat: float
    lon: float


@dataclass
class _Step:
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
    return [
        _pt(
            lat0 + (lat1 - lat0) * i / n,
            lon0 + (lon1 - lon0) * i / n,
            h0 + (h1 - h0) * i / n,
        )
        for i in range(n + 1)
    ]


def _noise_df(rows: list[tuple]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "lat": [float(r[0]) for r in rows],
            "lon": [float(r[1]) for r in rows],
            "time": [float(r[2]) for r in rows],
            "is_step": [bool(r[3]) for r in rows],
        }
    )


def _teleport_rows(*, is_step: bool) -> list[tuple[float, float, float, bool]]:
    return [
        (0.0, 0.0, _ts(10.0), False),
        (50.0, 0.0, _ts(10.0) + 10, is_step),
        (0.01, 0.0, _ts(12.0), False),
    ]


def _spike_rows(*, is_step: bool) -> list[tuple[float, float, float, bool]]:
    return [
        (0.0, 0.0, _ts(10.0), False),
        (0.0, 0.1, _ts(10.5), is_step),
        (0.0, 0.005, _ts(11.0), False),
    ]


def _assert_noise_value(
    rows: list[tuple[float, float, float, bool]],
    column: str,
    value: float,
    *,
    kept: bool,
) -> None:
    values = _remove_gps_noise(_noise_df(rows))[column].to_list()
    assert (value in values) is kept


def _segment_kinds(steps: list[_Step], gps: list[Point]) -> set[SegmentKind]:
    return {s.kind for s in build_segments(steps, gps)}


def _hikes(steps: list[_Step], gps: list[Point]) -> list[SegmentData]:
    return [s for s in build_segments(steps, gps) if s.kind == SegmentKind.hike]


def _assert_segment_kind(
    steps: list[_Step],
    gps: list[Point],
    expected: SegmentKind,
    unexpected: SegmentKind | None = None,
) -> None:
    kinds = _segment_kinds(steps, gps)
    assert expected in kinds
    if unexpected is not None:
        assert unexpected not in kinds


class TestNoiseRemoval:
    def test_teleport_removed(self) -> None:
        _assert_noise_value(_teleport_rows(is_step=False), "lat", 50.0, kept=False)

    def test_teleport_kept_when_step(self) -> None:
        _assert_noise_value(_teleport_rows(is_step=True), "lat", 50.0, kept=True)

    def test_spike_removed(self) -> None:
        _assert_noise_value(_spike_rows(is_step=False), "lon", 0.1, kept=False)

    def test_spike_kept_when_step(self) -> None:
        _assert_noise_value(_spike_rows(is_step=True), "lon", 0.1, kept=True)


class TestClassification:
    def test_no_other_kind_in_output(self) -> None:
        gps = (
            _track(0.0, 0.0, 0.0, 0.01, h0=8.0, h1=9.0, n=10)
            + _track(0.0, 0.01, 0.0, 1.0, h0=9.5, h1=10.0, n=5)
            + _track(0.0, 1.0, 0.0, 1.01, h0=10.5, h1=11.5, n=10)
        )
        kinds = _segment_kinds([_step(0.0, 1.0, 10.0)], gps)
        assert all(k.value != "other" for k in kinds)

    def test_slow_short_movement_is_walking(self) -> None:
        _assert_segment_kind(
            [_step(0.0, 0.005, 9.5)],
            _track(0.0, 0.0, 0.0, 0.005, h0=9.0, h1=9.5, n=10),
            SegmentKind.walking,
            SegmentKind.hike,
        )

    def test_fast_movement_is_driving(self) -> None:
        _assert_segment_kind(
            [_step(0.0, 0.5, 9.5)],
            _track(0.0, 0.0, 0.0, 0.5, h0=9.0, h1=9.5, n=5),
            SegmentKind.driving,
            SegmentKind.hike,
        )

    def test_flight_speed_is_flight(self) -> None:
        _assert_segment_kind(
            [_step(0.0, 0.0, 9.0), _step(0.0, 5.0, 12.0)],
            [_pt(0.0, 0.0, hours=10.0), _pt(0.0, 5.0, hours=12.0)],
            SegmentKind.flight,
        )

    def test_pre_first_step_flight_not_dropped(self) -> None:
        gps_a = [_pt(32.0, 35.0, hours=0.0)]
        gps_b = _track(25.0, 55.0, 25.01, 55.01, h0=3.5, h1=8.0, n=20)
        gps_c = _track(-34.6, -58.4, -34.61, -58.41, h0=22.0, h1=26.0, n=20)

        steps = [_step(-34.6, -58.4, 22.0)]

        segments = list(build_segments(steps, gps_a + gps_b + gps_c))
        kinds = [s.kind for s in segments]
        assert kinds.count(SegmentKind.flight) >= 2, (
            f"Expected ≥2 flights in {kinds} - pre-first-step flights were dropped"
        )
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
        gps = _track(0.0, 0.0, 0.0, 0.2, h0=8.0, h1=14.0, n=50)
        assert _hikes([_step(0.0, 0.2, 14.0)], gps)

    def test_brief_transfer_between_hikes_absorbed(self) -> None:
        hike1 = _track(0.0, 0.0, 0.0, 0.05, h0=8.0, h1=11.0, n=30)
        taxi = [_pt(0.0, 0.05, hours=11.0), _pt(0.0, 0.08, hours=11.17)]
        hike2 = _track(0.0, 0.08, 0.0, 0.13, h0=11.17, h1=14.17, n=30)

        steps = [_step(0.0, 0.0, 8.0), _step(0.0, 0.13, 14.17)]
        hikes = _hikes(steps, hike1 + taxi + hike2)
        assert len(hikes) == 1, (
            f"Brief transfer should be absorbed into one hike, got {len(hikes)}"
        )


class TestHikeValidation:
    def test_below_min_duration_is_not_hike(self) -> None:
        gps = _track(0.0, 0.0, 0.0, 0.01, h0=9.0, h1=10.0, n=15)
        assert not _hikes([_step(0.0, 0.01, 10.0)], gps)

    def test_below_min_distance_is_not_hike(self) -> None:
        gps = _track(0.0, 0.0, 0.0, 0.009, h0=9.0, h1=12.0, n=30)
        assert not _hikes([_step(0.0, 0.009, 12.0)], gps)


def _point_near(
    points: list[Point], lat: float, lon: float, tol: float = 0.001
) -> bool:
    return any(abs(p.lat - lat) < tol and abs(p.lon - lon) < tol for p in points)


class TestStepPreservation:
    def test_step_in_out_and_back_hike(self) -> None:
        gps = _track(0.0, 0.0, 0.0, 0.09, h0=8.0, h1=11.0, n=20) + _track(
            0.0, 0.09, 0.0, 0.0, h0=13.0, h1=16.0, n=20
        )
        hikes = _hikes([_step(0.0, 0.15, 12.0)], gps)
        assert hikes
        assert _point_near(hikes[0].points, 0.0, 0.15)

    def test_step_included_when_edge_speed_above_hike_max(self) -> None:
        gps = _track(0.0, 0.0, 0.0, 0.05, h0=8.0, h1=13.0, n=30)
        hikes = _hikes([_step(0.0, 0.15, 13.5)], gps)
        assert hikes
        assert _point_near(hikes[0].points, 0.0, 0.15)


class TestHikePoints:
    def test_non_hike_segments_are_rdp_simplified(self) -> None:
        gps = _track(0.0, 0.0, 0.0, 0.5, h0=9.0, h1=9.5, n=50)
        segments = list(build_segments([_step(0.0, 0.5, 9.5)], gps))
        for seg in segments:
            if seg.kind != SegmentKind.hike:
                assert len(seg.points) <= 10


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


class TestRobustness:
    def test_no_gps_does_not_crash(self) -> None:
        steps = [_step(0.0, 0.0, 9.0), _step(0.0, 0.1, 14.0)]
        segments = list(build_segments(steps, []))
        assert all(len(s.points) >= 2 for s in segments)

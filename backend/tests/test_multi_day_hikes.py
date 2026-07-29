from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.logic.spatial.segments import build_segments
from app.logic.trip_processing import multi_day_hike_ranges, segment_timezone
from app.models.polarsteps import Point, PSLocations, PSTrip
from app.models.segment import Segment, SegmentData, SegmentKind
from tests.factories import make_segment


@pytest.fixture(scope="module")
def all_segments(sa_trip: PSTrip, sa_locations: PSLocations) -> list[SegmentData]:
    steps = sorted(sa_trip.all_steps, key=lambda s: s.timestamp)
    return list(build_segments(steps, sa_locations.locations))


_KM_PER_DEG_LAT = 111.32  # at equator


def _hike_seg(points: list[Point], tz: str = "America/Santiago") -> Segment:
    return make_segment(
        1,
        "trip1",
        start_time=points[0].time,
        end_time=points[-1].time,
        kind=SegmentKind.hike,
        timezone_id=tz,
        points=points,
    )


def _multi_day_seg(
    daily_km: list[float],
    start_date: date,
    tz: str = "America/Santiago",
) -> Segment:
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

    return _hike_seg(points, tz)


def _minimal_seg(
    kind: SegmentKind,
    start: float,
    end: float,
    tz: str = "America/Santiago",
) -> Segment:
    return make_segment(
        1,
        "trip1",
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
    def test_non_hike_segments_excluded(self) -> None:
        seg = _minimal_seg(SegmentKind.driving, 1e9, 1e9 + 4 * 86400)
        assert multi_day_hike_ranges([seg]) == []

    def test_uses_local_timezone_for_date(self) -> None:
        zone = ZoneInfo("America/Santiago")
        t1 = datetime(2024, 12, 8, 8, 0, tzinfo=zone).timestamp()
        t2 = datetime(2024, 12, 8, 23, 30, tzinfo=zone).timestamp()
        seg = _hike_seg(
            [
                Point(lat=0.0, lon=0.0, time=t1),
                Point(lat=0.072, lon=0.0, time=t2),
            ]
        )
        assert multi_day_hike_ranges([seg]) == []

    @pytest.mark.parametrize(
        ("daily_km", "start", "expected", "tz"),
        [
            (
                [14, 14, 14, 14],
                date(2024, 12, 8),
                [(date(2024, 12, 8), date(2024, 12, 11))],
                "America/Santiago",
            ),
            ([8.0], date(2024, 12, 8), [], "America/Santiago"),
            (
                [15, 14, 13, 14],
                date(2024, 12, 1),
                [(date(2024, 12, 1), date(2024, 12, 4))],
                "America/Santiago",
            ),
            (
                [2.5, 2.3],
                date(2025, 6, 10),
                [(date(2025, 6, 10), date(2025, 6, 11))],
                "America/Lima",
            ),
            (
                [12, 10, 11, 9, 10, 11, 10, 8],
                date(2025, 8, 10),
                [(date(2025, 8, 10), date(2025, 8, 17))],
                "America/Santiago",
            ),
            ([10.0, 1.5], date(2024, 12, 24), [], "America/Santiago"),
            (
                [6.0, 5.0],
                date(2025, 5, 14),
                [(date(2025, 5, 14), date(2025, 5, 15))],
                "America/Santiago",
            ),
            (
                [0.3, 0.4, 5.0, 0.2, 0.3, 0.3, 0.4, 0.3],
                date(2025, 1, 26),
                [],
                "America/Santiago",
            ),
        ],
    )
    def test_daily_distance_cases(
        self,
        daily_km: list[float],
        start: date,
        expected: list[tuple[date, date]],
        tz: str,
    ) -> None:
        assert multi_day_hike_ranges([_multi_day_seg(daily_km, start, tz)]) == expected

    def test_multiple_hikes(self) -> None:
        ranges = multi_day_hike_ranges(
            [
                _multi_day_seg([14, 14, 14, 14], date(2024, 12, 8)),
                _multi_day_seg([10, 10, 10, 10], date(2025, 1, 7)),
            ]
        )
        assert len(ranges) == 2

    def test_midnight_crossing_single_day_hike(self) -> None:
        zone = ZoneInfo("America/Santiago")
        d1 = date(2024, 11, 15)
        d2 = d1 + timedelta(days=1)
        t1 = datetime(d1.year, d1.month, d1.day, 18, 0, tzinfo=zone).timestamp()
        t2 = datetime(d1.year, d1.month, d1.day, 23, 59, tzinfo=zone).timestamp()
        t3 = datetime(d2.year, d2.month, d2.day, 6, 0, tzinfo=zone).timestamp()
        seg = _hike_seg(
            [
                Point(lat=0.0, lon=0.0, time=t1),
                Point(lat=0.072, lon=0.0, time=t2),
                Point(lat=0.081, lon=0.0, time=t3),
            ]
        )
        assert multi_day_hike_ranges([seg]) == []

    def test_gps_drift_crosses_midnight(self) -> None:
        zone = ZoneInfo("America/Santiago")
        d1 = date(2024, 12, 15)
        d2 = d1 + timedelta(days=1)
        t1 = datetime(d1.year, d1.month, d1.day, 14, 0, tzinfo=zone).timestamp()
        t_mid = datetime(d1.year, d1.month, d1.day, 23, 30, tzinfo=zone).timestamp()
        t2 = datetime(d2.year, d2.month, d2.day, 10, 0, tzinfo=zone).timestamp()
        seg = _hike_seg(
            [
                Point(lat=0.0, lon=0.0, time=t1),
                Point(lat=0.009, lon=0.0, time=t_mid),
                Point(lat=0.0135, lon=0.0, time=t2),
            ]
        )
        assert multi_day_hike_ranges([seg]) == []

    def test_adjacent_ranges_merged(self) -> None:
        seg1 = _multi_day_seg([6.0, 4.0], date(2025, 5, 25))
        seg2 = _multi_day_seg([3.0, 5.0], date(2025, 5, 26))
        ranges = multi_day_hike_ranges([seg1, seg2])
        assert ranges == [(date(2025, 5, 25), date(2025, 5, 27))]

    def test_non_overlapping_ranges_stay_separate(self) -> None:
        seg1 = _multi_day_seg([10, 10], date(2025, 4, 1))
        seg2 = _multi_day_seg([10, 10], date(2025, 4, 10))
        ranges = multi_day_hike_ranges([seg1, seg2])
        assert ranges == [
            (date(2025, 4, 1), date(2025, 4, 2)),
            (date(2025, 4, 10), date(2025, 4, 11)),
        ]


class TestMultiDayHikeRangesIntegration:
    @pytest.fixture(scope="class")
    def real_segments(
        self,
        sa_trip: PSTrip,
        all_segments: list[SegmentData],
    ) -> list[Segment]:
        steps = sa_trip.all_steps
        return [
            make_segment(
                1,
                "sa2024",
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
        expected_good = [
            (date(2024, 12, 1), date(2024, 12, 4)),
            (date(2024, 12, 8), date(2024, 12, 11)),
        ]
        for start, end in expected_good:
            assert any(s <= start and end <= e for s, e in real_ranges), (
                f"Missing confirmed hike {start} -> {end}"
            )

    def test_split_hike_merged(self, real_ranges: list[tuple[date, date]]) -> None:
        assert (date(2025, 5, 25), date(2025, 5, 26)) not in real_ranges
        assert (date(2025, 5, 26), date(2025, 5, 27)) not in real_ranges
        assert any(
            s <= date(2025, 5, 25) and date(2025, 5, 27) <= e for s, e in real_ranges
        ), "May 25-27 merged range missing"

"""Unit tests for segment boundary adjustment logic."""

import pytest
from pydantic import ValidationError

from app.models.polarsteps import Point
from app.models.segment import BoundaryAdjust, Segment, SegmentKind, split_segments


def _seg(kind: str, points: list[tuple[float, float, float]]) -> Segment:
    pts = [Point(lat=lat, lon=lon, time=t) for lat, lon, t in points]
    return Segment(
        uid=1,
        aid="test",
        start_time=pts[0].time,
        end_time=pts[-1].time,
        kind=SegmentKind(kind),
        timezone_id="UTC",
        points=pts,
    )


class TestBoundarySplit:
    """Tests for the boundary split logic."""

    def test_extend_hike_start_backward(self) -> None:
        """Moving start handle backward extends the hike."""
        walking = _seg("walking", [(0, 0, 10), (0, 1, 20), (0, 2, 30), (0, 3, 40)])
        hike = _seg("hike", [(0, 4, 50), (0, 5, 60), (0, 6, 70)])

        earlier, later = split_segments(hike, walking, 20)

        assert earlier.kind == "walking"
        assert len(earlier.points) == 2
        assert earlier.end_time == 20

        assert later.kind == "hike"
        assert len(later.points) == 5
        assert later.start_time == 30

    def test_shrink_hike_start_forward(self) -> None:
        """Moving start handle forward shrinks the hike."""
        walking = _seg("walking", [(0, 0, 10), (0, 1, 20)])
        hike = _seg("hike", [(0, 2, 30), (0, 3, 40), (0, 4, 50), (0, 5, 60)])

        earlier, later = split_segments(hike, walking, 40)

        assert earlier.kind == "walking"
        assert len(earlier.points) == 4
        assert earlier.end_time == 40

        assert later.kind == "hike"
        assert len(later.points) == 2
        assert later.start_time == 50

    def test_extend_hike_end_forward(self) -> None:
        """Moving end handle forward extends the hike."""
        hike = _seg("hike", [(0, 0, 10), (0, 1, 20), (0, 2, 30)])
        walking = _seg("walking", [(0, 3, 40), (0, 4, 50), (0, 5, 60)])

        earlier, later = split_segments(hike, walking, 40)

        assert earlier.kind == "hike"
        assert len(earlier.points) == 4
        assert earlier.end_time == 40

        assert later.kind == "walking"
        assert len(later.points) == 2
        assert later.start_time == 50

    def test_shrink_hike_end_backward(self) -> None:
        """Moving end handle backward shrinks the hike."""
        hike = _seg("hike", [(0, 0, 10), (0, 1, 20), (0, 2, 30), (0, 3, 40)])
        walking = _seg("walking", [(0, 4, 50), (0, 5, 60)])

        earlier, later = split_segments(hike, walking, 20)

        assert earlier.kind == "hike"
        assert len(earlier.points) == 2
        assert earlier.end_time == 20

        assert later.kind == "walking"
        assert len(later.points) == 4
        assert later.start_time == 30

    def test_too_few_points_raises(self) -> None:
        """Both segments must retain >= 2 points after split."""
        walking = _seg("walking", [(0, 0, 10), (0, 1, 20)])
        hike = _seg("hike", [(0, 2, 30), (0, 3, 40)])

        with pytest.raises(ValueError, match="2 points"):
            split_segments(hike, walking, 30)

    def test_times_are_correct(self) -> None:
        """Start/end times match the actual first/last point times."""
        walking = _seg("walking", [(0, 0, 100), (0, 1, 200), (0, 2, 300)])
        hike = _seg("hike", [(0, 3, 400), (0, 4, 500), (0, 5, 600)])

        earlier, later = split_segments(hike, walking, 200)

        assert earlier.start_time == 100
        assert earlier.end_time == 200
        assert later.start_time == 300
        assert later.end_time == 600

    def test_interpolates_boundary_between_points(self) -> None:
        """Interpolated point is created between GPS points."""
        hike = _seg("hike", [(0, 0, 10), (0, 10, 20), (0, 20, 30)])
        walking = _seg("walking", [(0, 30, 40), (0, 40, 50), (0, 50, 60)])

        earlier, later = split_segments(hike, walking, 25)

        assert earlier.kind == "hike"
        assert len(earlier.points) == 3
        assert earlier.end_time == 25
        # halfway between lon=10 and lon=20
        assert earlier.points[-1].lon == pytest.approx(15.0)

        assert later.kind == "walking"
        assert len(later.points) == 5
        assert later.start_time == 25

    def test_no_interpolation_on_exact_point(self) -> None:
        """No extra point when boundary lands on a GPS point."""
        hike = _seg("hike", [(0, 0, 10), (0, 10, 20), (0, 20, 30)])
        walking = _seg("walking", [(0, 30, 40), (0, 40, 50)])

        earlier, later = split_segments(hike, walking, 20)

        assert len(earlier.points) == 2  # [10, 20]
        assert len(later.points) == 3  # [30, 40, 50]

    def test_boundary_in_gap_raises(self) -> None:
        """Boundary in gap between segments is rejected."""
        walking = _seg("walking", [(0, 0, 10), (0, 1, 20)])
        hike = _seg("hike", [(0, 5, 50), (0, 6, 60)])

        with pytest.raises(ValueError, match="gap"):
            split_segments(hike, walking, 35)

    def test_boundary_adjust_model(self) -> None:
        """BoundaryAdjust schema validates correctly."""
        adj = BoundaryAdjust(
            start_time=100.0,
            end_time=200.0,
            handle="start",
            new_boundary_time=150.0,
        )
        assert adj.handle == "start"
        assert adj.new_boundary_time == 150.0

        with pytest.raises(ValidationError, match="literal_error"):
            BoundaryAdjust(
                start_time=100.0,
                end_time=200.0,
                handle="invalid",
                new_boundary_time=150.0,
            )

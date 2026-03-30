from app.logic.matching import (
    is_sparse,
    reduce_coords,
    simplify_route,
)

Coords = list[tuple[float, float]]


class TestIsSparse:
    def test_dense_trace(self) -> None:
        # 5 points, ~0.5km apart -> dense
        coords: Coords = [
            (4.0, 52.0), (4.005, 52.0), (4.01, 52.0), (4.015, 52.0), (4.02, 52.0)
        ]
        assert not is_sparse(coords)

    def test_sparse_trace(self) -> None:
        # 3 points, ~100km apart -> sparse
        coords: Coords = [(4.0, 52.0), (5.0, 52.0), (6.0, 52.0)]
        assert is_sparse(coords)

    def test_single_point(self) -> None:
        assert not is_sparse([(4.0, 52.0)])


class TestReduceCoords:
    def test_under_limit_unchanged(self) -> None:
        coords: Coords = [(4.0, 52.0), (4.01, 52.01)]
        assert reduce_coords(coords, 100) == coords

    def test_over_limit_reduced(self) -> None:
        coords: Coords = [(i * 0.001, 52.0) for i in range(200)]
        result = reduce_coords(coords, 100)
        assert len(result) <= 100
        # First and last preserved
        assert result[0] == coords[0]
        assert result[-1] == coords[-1]


class TestSimplifyRoute:
    def test_short_segment_fine_tolerance(self) -> None:
        # < 10km segment should use ~5m tolerance
        coords: Coords = [(4.0 + i * 0.0001, 52.0 + i * 0.0001) for i in range(50)]
        result = simplify_route(coords, span_km=5.0)
        assert len(result) < len(coords)
        assert len(result) >= 2

    def test_long_segment_coarse_tolerance(self) -> None:
        # >= 100km segment should use ~50m tolerance
        coords: Coords = [(4.0 + i * 0.01, 52.0 + i * 0.01) for i in range(100)]
        result = simplify_route(coords, span_km=150.0)
        assert len(result) < len(coords)

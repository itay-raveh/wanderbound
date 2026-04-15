"""Unit tests for the photo matching algorithm.

Tests pure computation: time-window bucketing, distance matrix building,
Hungarian matching, and threshold rejection.
"""

import imagehash
import numpy as np

from app.logic.photo_upgrade import (
    build_cost_matrix,
    build_step_windows,
    match_within_window,
)


def _make_hash(value: int) -> imagehash.ImageHash:
    """Create a deterministic hash for testing."""
    bits = np.array([(value >> i) & 1 for i in range(64)], dtype=bool)
    return imagehash.ImageHash(bits)


class TestBuildStepWindows:
    def test_single_step_gets_24h_window(self) -> None:
        windows = build_step_windows(
            step_timestamps=[1_700_000_000.0],
            step_ids=[1],
        )
        assert len(windows) == 1
        assert windows[0].step_id == 1
        assert windows[0].start == 1_700_000_000.0
        assert windows[0].end == 1_700_000_000.0 + 86400 + 30 * 60

    def test_two_steps_use_next_start_as_end(self) -> None:
        windows = build_step_windows(
            step_timestamps=[1_700_000_000.0, 1_700_050_000.0],
            step_ids=[1, 2],
        )
        assert len(windows) == 2
        assert windows[0].end == 1_700_050_000.0 + 30 * 60
        assert windows[1].end == 1_700_050_000.0 + 86400 + 30 * 60

    def test_overlap_margin_extends_boundaries(self) -> None:
        windows = build_step_windows(
            step_timestamps=[1_700_000_000.0, 1_700_050_000.0],
            step_ids=[1, 2],
        )
        margin = 30 * 60  # 30 minutes
        boundary_time = 1_700_050_000.0
        assert windows[0].contains(boundary_time - 1)
        assert windows[0].contains(boundary_time + margin - 1)


class TestBuildCostMatrix:
    def test_identical_hashes_produce_zero_cost(self) -> None:
        h = _make_hash(0xFF00FF00FF00FF00)
        matrix = build_cost_matrix(
            local_hashes=[h],
            candidate_hashes=[h],
        )
        assert matrix[0][0] == 0

    def test_completely_different_hashes_produce_high_cost(self) -> None:
        h1 = _make_hash(0x0)
        h2 = _make_hash(0xFFFFFFFFFFFFFFFF)
        matrix = build_cost_matrix(
            local_hashes=[h1],
            candidate_hashes=[h2],
        )
        assert matrix[0][0] == 64  # all bits differ

    def test_matrix_shape_matches_inputs(self) -> None:
        hashes = [_make_hash(i) for i in range(3)]
        candidates = [_make_hash(i + 100) for i in range(5)]
        matrix = build_cost_matrix(hashes, candidates)
        assert len(matrix) == 3
        assert len(matrix[0]) == 5


class TestMatchWithinWindow:
    def test_perfect_matches_all_paired(self) -> None:
        h = _make_hash(42)
        results = match_within_window(
            local_names=["photo1.jpg", "photo2.jpg"],
            local_hashes=[h, h],
            candidate_ids=["gp-1", "gp-2"],
            candidate_hashes=[h, h],
        )
        assert len(results) == 2
        assert all(r.distance == 0 for r in results)

    def test_above_threshold_rejected(self) -> None:
        h1 = _make_hash(0x0)
        h2 = _make_hash(0xFFFFFFFFFFFFFFFF)
        results = match_within_window(
            local_names=["photo1.jpg"],
            local_hashes=[h1],
            candidate_ids=["gp-1"],
            candidate_hashes=[h2],
        )
        assert len(results) == 0

    def test_optimal_assignment_not_greedy(self) -> None:
        """Hungarian algorithm should find global optimum, not greedy local."""
        h_base = _make_hash(0)

        bits_p1 = np.array([(0 >> i) & 1 for i in range(64)], dtype=bool)
        bits_p1[0] = True
        bits_p1[1] = True  # distance 2 from all-zero
        h_p1 = imagehash.ImageHash(bits_p1)

        bits_p2 = np.zeros(64, dtype=bool)
        bits_p2[0] = True  # distance 1 from all-zero
        h_p2 = imagehash.ImageHash(bits_p2)

        bits_gp2 = np.zeros(64, dtype=bool)
        bits_gp2[0] = True
        bits_gp2[1] = True
        bits_gp2[2] = True  # distance 3 from p1
        h_gp2 = imagehash.ImageHash(bits_gp2)

        results = match_within_window(
            local_names=["photo1.jpg", "photo2.jpg"],
            local_hashes=[h_p1, h_p2],
            candidate_ids=["gp-1", "gp-2"],
            candidate_hashes=[h_base, h_gp2],
        )
        matched_locals = {r.local_name for r in results}
        assert "photo1.jpg" in matched_locals
        assert "photo2.jpg" in matched_locals

    def test_empty_inputs_return_empty(self) -> None:
        results = match_within_window(
            local_names=[],
            local_hashes=[],
            candidate_ids=["gp-1"],
            candidate_hashes=[_make_hash(0)],
        )
        assert results == []

    def test_more_candidates_than_locals(self) -> None:
        h = _make_hash(42)
        results = match_within_window(
            local_names=["photo1.jpg"],
            local_hashes=[h],
            candidate_ids=["gp-1", "gp-2", "gp-3"],
            candidate_hashes=[_make_hash(99), h, _make_hash(88)],
        )
        assert len(results) == 1
        assert results[0].google_id == "gp-2"
        assert results[0].distance == 0

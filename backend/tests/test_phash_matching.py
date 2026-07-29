from pathlib import Path
from unittest.mock import patch

import imagehash
import numpy as np
from PIL import Image
from PIL.ExifTags import Base as ExifBase

from app.logic.media_upgrade import phash_matching
from app.logic.media_upgrade.phash_matching import (
    compute_phash_from_path,
)

from .media_upgrade_helpers import (
    hashed_media as _hm,
    make_hash as _make_hash,
)


class TestComputePhash:
    def test_orientation_invariant(self, tmp_path: Path) -> None:
        upright = Image.new("RGB", (100, 200), color="white")
        for x in range(100):
            for y in range(80):
                upright.putpixel((x, y), (0, 0, 0))

        upright_path = tmp_path / "upright.jpg"
        upright.save(upright_path, "JPEG", quality=95)

        sideways = upright.transpose(Image.Transpose.ROTATE_270)
        exif = sideways.getexif()
        exif[ExifBase.Orientation] = 6
        sideways_path = tmp_path / "sideways.jpg"
        sideways.save(sideways_path, "JPEG", quality=95, exif=exif.tobytes())

        h_upright = compute_phash_from_path(upright_path)
        h_sideways = compute_phash_from_path(sideways_path)

        assert h_upright - h_sideways <= 4


class TestGlobalMatching:
    def test_cost_matrix_uses_compact_numeric_storage(self) -> None:
        matrix = phash_matching.build_cost_matrix(
            [_hm("local.jpg", _make_hash(0))],
            [_hm("google-photo", _make_hash(1))],
        )

        assert isinstance(matrix, np.ndarray)
        assert matrix.dtype == np.int16
        assert matrix.tolist() == [[1]]

    def test_cost_matrix_vectorizes_single_hash_distances(self) -> None:
        local = [
            _hm("a.jpg", _make_hash(0)),
            _hm("b.jpg", _make_hash((1 << 64) - 1)),
        ]
        candidates = [
            _hm("google-a", _make_hash(1)),
            _hm("google-b", _make_hash((1 << 63) - 1)),
        ]

        with patch.object(
            phash_matching.np,
            "bitwise_count",
            wraps=np.bitwise_count,
        ) as bitwise_count:
            matrix = phash_matching.build_cost_matrix(local, candidates)

        assert bitwise_count.called
        assert matrix.tolist() == [[1, 63], [63, 1]]

    def test_thresholded_assignment_does_not_allocate_augmented_dense_matrix(
        self,
    ) -> None:
        cost = np.array([[0, 13, 12], [12, 0, 13]], dtype=np.int16)

        with patch.object(phash_matching.np, "full", wraps=np.full) as full:
            rows, cols = phash_matching._thresholded_assignment(cost, threshold=12)

        assert all(call.args[0] != (2, 5) for call in full.call_args_list)
        assert set(zip(rows.tolist(), cols.tolist(), strict=True)) == {
            (0, 0),
            (1, 1),
        }

    def test_thresholded_assignment_maximizes_valid_pair_count(self) -> None:
        cost = np.array([[0, 12], [12, 13]], dtype=np.int16)

        rows, cols = phash_matching._thresholded_assignment(cost, threshold=12)

        assert set(zip(rows.tolist(), cols.tolist(), strict=True)) == {
            (0, 1),
            (1, 0),
        }

    def test_thresholded_assignment_leaves_invalid_rows_unmatched(self) -> None:
        cost = np.array([[13, 20], [0, 4]], dtype=np.int16)

        rows, cols = phash_matching._thresholded_assignment(cost, threshold=12)

        assert list(zip(rows.tolist(), cols.tolist(), strict=True)) == [(1, 0)]

    def test_thresholded_assignment_handles_more_than_one_hundred_pairs(
        self,
    ) -> None:
        count = 101
        cost = np.full((count, count), 13, dtype=np.int16)
        np.fill_diagonal(cost, 0)

        rows, cols = phash_matching._thresholded_assignment(cost, threshold=12)

        assert len(rows) == count
        assert np.array_equal(rows, cols)

    def test_thresholded_assignment_handles_observed_large_selection(self) -> None:
        local_count = 401
        candidate_count = 1_400
        cost = np.full((local_count, candidate_count), 13, dtype=np.int16)
        diagonal = np.arange(local_count)
        cost[diagonal, diagonal] = 0

        rows, cols = phash_matching._thresholded_assignment(cost, threshold=12)

        assert np.array_equal(rows, diagonal)
        assert np.array_equal(cols, diagonal)

    def test_global_matching_is_independent_of_candidate_order(self) -> None:
        local = [
            _hm("a.jpg", _make_hash(0)),
            _hm("b.jpg", _make_hash((1 << 64) - 1)),
        ]
        forward = [
            _hm("google-a", _make_hash(0)),
            _hm("google-b", _make_hash((1 << 64) - 1)),
        ]

        first = phash_matching.match_media_globally(local, forward).matches
        second = phash_matching.match_media_globally(
            local, list(reversed(forward))
        ).matches

        assert {(match.local_name, match.google_id) for match in first} == {
            ("a.jpg", "google-a"),
            ("b.jpg", "google-b"),
        }
        assert {(match.local_name, match.google_id) for match in second} == {
            ("a.jpg", "google-a"),
            ("b.jpg", "google-b"),
        }

    def test_optimal_assignment_not_greedy(self) -> None:
        h_base = _make_hash(0)

        bits_p1 = np.array([(0 >> i) & 1 for i in range(64)], dtype=bool)
        bits_p1[0] = True
        bits_p1[1] = True
        h_p1 = imagehash.ImageHash(bits_p1)

        bits_p2 = np.zeros(64, dtype=bool)
        bits_p2[0] = True
        h_p2 = imagehash.ImageHash(bits_p2)

        bits_gp2 = np.zeros(64, dtype=bool)
        bits_gp2[0] = True
        bits_gp2[1] = True
        bits_gp2[2] = True
        h_gp2 = imagehash.ImageHash(bits_gp2)

        results = phash_matching.match_media_globally(
            [_hm("photo1.jpg", h_p1), _hm("photo2.jpg", h_p2)],
            [_hm("gp-1", h_base), _hm("gp-2", h_gp2)],
        ).matches
        matched_locals = {result.local_name for result in results}
        assert "photo1.jpg" in matched_locals
        assert "photo2.jpg" in matched_locals

"""Unit tests for media matching and processing.

Tests pure computation: time-window bucketing, distance matrix building,
Hungarian matching, threshold rejection, cross-step fallback, video frame
extraction, and post-download photo processing (EXIF strip, resize,
format conversion).
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import imagehash
import numpy as np
import pytest
from PIL import Image
from PIL.ExifTags import Base as ExifBase

from app.logic.layout.media import Media
from app.logic.media_upgrade.phash_matching import (
    _CROSS_TYPE_COST,
    _FALLBACK_MAX_DIMENSION,
    MATCH_THRESHOLD,
    HashedMedia,
    MatchResult,
    _pairwise_distance,
    _parse_timestamp,
    bucket_by_window,
    build_cost_matrix,
    build_step_windows,
    cross_step_fallback,
    match_within_window,
)
from app.logic.media_upgrade.pipeline import apply_upgrade_results
from app.logic.media_upgrade.processing import (
    _MAX_LONG_EDGE,
    process_photo_sync,
    process_video,
)
from app.services.google_photos import (
    GoogleMediaFile,
    GoogleMediaType,
    PickedMediaItem,
)

from .factories import create_test_jpeg


def _make_hash(value: int) -> imagehash.ImageHash:
    """Create a deterministic hash for testing."""
    bits = np.array([(value >> i) & 1 for i in range(64)], dtype=bool)
    return imagehash.ImageHash(bits)


def _hm(
    key: str,
    h: imagehash.ImageHash | list[imagehash.ImageHash],
    *,
    video: bool = False,
) -> HashedMedia:
    return HashedMedia(key=key, hash=h, is_video=video)


class TestBuildStepWindows:
    def test_single_step_gets_24h_window(self) -> None:
        margin = 30 * 60
        windows = build_step_windows(
            step_timestamps=[1_700_000_000.0],
            step_ids=[1],
        )
        assert len(windows) == 1
        assert windows[0].step_id == 1
        assert windows[0].start == 1_700_000_000.0 - margin
        assert windows[0].end == 1_700_000_000.0 + 86400 + margin

    def test_first_window_extends_backward(self) -> None:
        margin = 30 * 60
        windows = build_step_windows(
            step_timestamps=[1_700_000_000.0, 1_700_050_000.0],
            step_ids=[1, 2],
        )
        assert windows[0].start == 1_700_000_000.0 - margin
        assert windows[1].start == 1_700_050_000.0

    def test_two_steps_use_next_start_as_end(self) -> None:
        margin = 30 * 60
        windows = build_step_windows(
            step_timestamps=[1_700_000_000.0, 1_700_050_000.0],
            step_ids=[1, 2],
        )
        assert len(windows) == 2
        assert windows[0].end == 1_700_050_000.0 + margin
        assert windows[1].end == 1_700_050_000.0 + 86400 + margin

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
        matrix = build_cost_matrix([_hm("a", h)], [_hm("b", h)])
        assert matrix[0][0] == 0

    def test_completely_different_hashes_produce_high_cost(self) -> None:
        h1 = _make_hash(0x0)
        h2 = _make_hash(0xFFFFFFFFFFFFFFFF)
        matrix = build_cost_matrix([_hm("a", h1)], [_hm("b", h2)])
        assert matrix[0][0] == 64  # all bits differ

    def test_matrix_shape_matches_inputs(self) -> None:
        local_media = [_hm(f"l{i}", _make_hash(i)) for i in range(3)]
        cands = [_hm(f"c{i}", _make_hash(i + 100)) for i in range(5)]
        matrix = build_cost_matrix(local_media, cands)
        assert len(matrix) == 3
        assert len(matrix[0]) == 5


class TestPairwiseDistance:
    def test_empty_frame_list_returns_cross_type_cost(self) -> None:
        candidate = _make_hash(42)
        assert _pairwise_distance([], candidate) == _CROSS_TYPE_COST

    def test_single_frame_returns_hamming_distance(self) -> None:
        local = _make_hash(0xFF)
        candidate = _make_hash(0xFF)
        assert _pairwise_distance([local], candidate) == 0

    def test_multi_frame_returns_minimum(self) -> None:
        close = _make_hash(0xFF00)
        far = _make_hash(0x0)
        candidate = _make_hash(0xFF00)
        assert _pairwise_distance([far, close], candidate) == 0


class TestMatchWithinWindow:
    def test_perfect_matches_all_paired(self) -> None:
        h = _make_hash(42)
        results = match_within_window(
            [_hm("photo1.jpg", h), _hm("photo2.jpg", h)],
            [_hm("gp-1", h), _hm("gp-2", h)],
        )
        assert len(results) == 2
        assert all(r.distance == 0 for r in results)

    def test_above_threshold_rejected(self) -> None:
        h1 = _make_hash(0x0)
        h2 = _make_hash(0xFFFFFFFFFFFFFFFF)
        results = match_within_window([_hm("photo1.jpg", h1)], [_hm("gp-1", h2)])
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
            [_hm("photo1.jpg", h_p1), _hm("photo2.jpg", h_p2)],
            [_hm("gp-1", h_base), _hm("gp-2", h_gp2)],
        )
        matched_locals = {r.local_name for r in results}
        assert "photo1.jpg" in matched_locals
        assert "photo2.jpg" in matched_locals

    def test_empty_inputs_return_empty(self) -> None:
        results = match_within_window([], [_hm("gp-1", _make_hash(0))])
        assert results == []

    def test_more_candidates_than_locals(self) -> None:
        h = _make_hash(42)
        results = match_within_window(
            [_hm("photo1.jpg", h)],
            [_hm("gp-1", _make_hash(99)), _hm("gp-2", h), _hm("gp-3", _make_hash(88))],
        )
        assert len(results) == 1
        assert results[0].google_id == "gp-2"
        assert results[0].distance == 0


class TestMediaAwareCostMatrix:
    def test_single_hash_unchanged(self) -> None:
        """Photo-to-photo matching works as before."""
        h = _make_hash(0xFF00FF00FF00FF00)
        matrix = build_cost_matrix([_hm("a", h)], [_hm("b", h)])
        assert matrix[0][0] == 0

    def test_video_uses_minimum_distance(self) -> None:
        """Video cost is min distance across sampled frames."""
        h_close = _make_hash(42)
        h_far = _make_hash(0xFFFFFFFFFFFFFFFF)
        matrix = build_cost_matrix(
            [_hm("v", [h_far, h_close, h_far, h_far], video=True)],
            [_hm("c", _make_hash(42), video=True)],
        )
        assert matrix[0][0] == 0  # min of distances, h_close matches exactly

    def test_cross_type_gets_infinite_cost(self) -> None:
        """Photo-to-video pairs get cost above threshold."""
        h = _make_hash(42)
        matrix = build_cost_matrix([_hm("a", h)], [_hm("b", h, video=True)])
        assert matrix[0][0] > MATCH_THRESHOLD

    def test_video_to_photo_gets_infinite_cost(self) -> None:
        h = _make_hash(42)
        matrix = build_cost_matrix([_hm("v", [h, h, h, h], video=True)], [_hm("c", h)])
        assert matrix[0][0] > MATCH_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers for bucketing / fallback tests
# ---------------------------------------------------------------------------


def _make_item(
    item_id: str,
    create_time: str,
    *,
    item_type: GoogleMediaType = "PHOTO",
    video_processing_status: str | None = None,
) -> PickedMediaItem:
    return PickedMediaItem(
        id=item_id,
        create_time=create_time,
        type=item_type,
        media_file=GoogleMediaFile(
            base_url="https://lh3.googleusercontent.com/test",
            mime_type="video/mp4" if item_type == "VIDEO" else "image/jpeg",
            filename=f"{item_id}.mp4" if item_type == "VIDEO" else f"{item_id}.jpg",
        ),
        video_processing_status=video_processing_status,
    )


class TestParseTimestamp:
    def test_iso_utc(self) -> None:
        ts = _parse_timestamp("2024-01-15T10:30:00+00:00")
        assert ts is not None
        assert abs(ts - 1705314600.0) < 1

    def test_iso_with_timezone(self) -> None:
        ts = _parse_timestamp("2024-01-15T12:30:00+02:00")
        assert ts is not None
        # 12:30 UTC+2 = 10:30 UTC
        assert abs(ts - 1705314600.0) < 1

    def test_invalid_returns_none(self) -> None:
        assert _parse_timestamp("not-a-date") is None
        assert _parse_timestamp("") is None


class TestBucketByWindow:
    def test_item_lands_in_correct_window(self) -> None:
        windows = build_step_windows(
            step_timestamps=[1_000_000.0, 1_050_000.0],
            step_ids=[1, 2],
        )
        item = _make_item("g1", "1970-01-12T19:20:00+00:00")  # epoch 1_020_000
        bucketed = bucket_by_window([item], windows)
        assert len(bucketed[1]) == 1
        assert bucketed[1][0].id == "g1"

    def test_video_without_status_accepted(self) -> None:
        """Videos with no processing status (None) are accepted."""
        windows = build_step_windows(
            step_timestamps=[1_000_000.0],
            step_ids=[1],
        )
        video = _make_item("v1", "1970-01-12T13:46:40+00:00", item_type="VIDEO")
        bucketed = bucket_by_window([video], windows)
        assert len(bucketed[1]) == 1

    def test_ready_video_accepted(self) -> None:
        windows = build_step_windows(
            step_timestamps=[1_000_000.0],
            step_ids=[1],
        )
        video = _make_item(
            "v1",
            "1970-01-12T13:46:40+00:00",
            item_type="VIDEO",
            video_processing_status="READY",
        )
        bucketed = bucket_by_window([video], windows)
        assert len(bucketed[1]) == 1
        assert bucketed[1][0].id == "v1"

    def test_processing_video_skipped(self) -> None:
        windows = build_step_windows(
            step_timestamps=[1_000_000.0],
            step_ids=[1],
        )
        video = _make_item(
            "v1",
            "1970-01-12T13:46:40+00:00",
            item_type="VIDEO",
            video_processing_status="PROCESSING",
        )
        bucketed = bucket_by_window([video], windows)
        assert len(bucketed[1]) == 0

    def test_failed_video_skipped(self) -> None:
        windows = build_step_windows(
            step_timestamps=[1_000_000.0],
            step_ids=[1],
        )
        video = _make_item(
            "v1",
            "1970-01-12T13:46:40+00:00",
            item_type="VIDEO",
            video_processing_status="FAILED",
        )
        bucketed = bucket_by_window([video], windows)
        assert len(bucketed[1]) == 0

    def test_invalid_timestamp_skipped(self) -> None:
        windows = build_step_windows(
            step_timestamps=[1_000_000.0],
            step_ids=[1],
        )
        bad = _make_item("b1", "not-a-timestamp")
        bucketed = bucket_by_window([bad], windows)
        assert len(bucketed[1]) == 0

    def test_overlap_margin_includes_boundary_items(self) -> None:
        """Items just past a window boundary should still match via overlap."""
        windows = build_step_windows(
            step_timestamps=[1_000_000.0, 1_050_000.0],
            step_ids=[1, 2],
        )
        # Item at exactly 1_050_000 + 10 min (within 30-min overlap of window 1)
        t = 1_050_000.0 + 600
        iso = datetime.fromtimestamp(t, UTC).isoformat()
        item = _make_item("g1", iso)
        bucketed = bucket_by_window([item], windows)
        # Should land in window 1 (via overlap) and also window 2
        assert any(i.id == "g1" for i in bucketed[1])
        assert any(i.id == "g1" for i in bucketed[2])


class TestCrossStepFallback:
    def test_matches_remaining_unmatched(self) -> None:
        """Unmatched photos get a second chance across all windows."""
        h = _make_hash(42)
        all_matches: list[MatchResult] = []
        matched_locals: set[str] = set()
        matched_candidates: set[str] = set()

        local_hashes = {"photo1.jpg": h}
        candidate_hashes = {"gp-1": h}
        item = _make_item("gp-1", "2024-01-15T10:00:00Z")

        cross_step_fallback(
            all_matches,
            matched_locals,
            matched_candidates,
            media_names=["photo1.jpg"],
            local_hashes=local_hashes,
            candidate_hashes=candidate_hashes,
            google_items=[item],
        )

        assert len(all_matches) == 1
        assert all_matches[0].local_name == "photo1.jpg"
        assert all_matches[0].google_id == "gp-1"

    def test_skips_already_matched(self) -> None:
        h = _make_hash(42)
        all_matches: list[MatchResult] = []
        matched_locals = {"photo1.jpg"}
        matched_candidates = {"gp-1"}

        cross_step_fallback(
            all_matches,
            matched_locals,
            matched_candidates,
            media_names=["photo1.jpg"],
            local_hashes={"photo1.jpg": h},
            candidate_hashes={"gp-1": h},
            google_items=[_make_item("gp-1", "2024-01-15T10:00:00Z")],
        )

        assert len(all_matches) == 0

    def test_runs_at_exact_dimension_limit(self) -> None:
        """Fallback still runs when both dimensions are exactly at the limit."""
        h = _make_hash(0)
        n = _FALLBACK_MAX_DIMENSION
        names = [f"photo{i}.jpg" for i in range(n)]
        hashes = dict.fromkeys(names, h)
        items = [_make_item(f"gp-{i}", "2024-01-15T10:00:00Z") for i in range(n)]
        candidate_hashes = {f"gp-{i}": h for i in range(n)}

        all_matches: list[MatchResult] = []
        cross_step_fallback(
            all_matches,
            matched_locals=set(),
            matched_candidates=set(),
            media_names=names,
            local_hashes=hashes,
            candidate_hashes=candidate_hashes,
            google_items=items,
        )

        assert len(all_matches) == n

    def test_skips_when_exceeding_dimension_limit(self) -> None:
        """Fallback is skipped when matrix would be too large."""
        h = _make_hash(0)
        n = _FALLBACK_MAX_DIMENSION + 1
        names = [f"photo{i}.jpg" for i in range(n)]
        hashes = dict.fromkeys(names, h)
        items = [_make_item(f"gp-{i}", "2024-01-15T10:00:00Z") for i in range(n)]
        candidate_hashes = {f"gp-{i}": h for i in range(n)}

        all_matches: list[MatchResult] = []
        cross_step_fallback(
            all_matches,
            matched_locals=set(),
            matched_candidates=set(),
            media_names=names,
            local_hashes=hashes,
            candidate_hashes=candidate_hashes,
            google_items=items,
        )

        assert len(all_matches) == 0


# ---------------------------------------------------------------------------
# Photo processing (EXIF strip, resize, JPEG conversion)
# ---------------------------------------------------------------------------


def _write_jpeg(
    path: Path, width: int, height: int, *, exif: bytes | None = None
) -> None:
    """Write a JPEG image to *path*, optionally with EXIF data."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    kwargs: dict = {"format": "JPEG", "quality": 95}
    if exif is not None:
        kwargs["exif"] = exif
    img.save(path, **kwargs)


def _write_png(path: Path, width: int, height: int) -> None:
    """Write a PNG image to *path*."""
    img = Image.new("RGBA", (width, height), color=(100, 150, 200, 255))
    img.save(path, format="PNG")


class TestProcessPhoto:
    def test_strips_exif(self, tmp_path: Path) -> None:
        """EXIF metadata must be removed."""
        img = Image.new("RGB", (800, 600))
        exif = img.getexif()
        exif[ExifBase.Make] = "TestCamera"
        exif[ExifBase.Model] = "X100"
        exif[ExifBase.Software] = "TestSuite"
        exif_bytes = exif.tobytes()

        raw = tmp_path / "in.jpg"
        out = tmp_path / "out.jpg"
        _write_jpeg(raw, 800, 600, exif=exif_bytes)

        with Image.open(raw) as src:
            assert len(src.getexif()) > 0

        process_photo_sync(raw, out)

        with Image.open(out) as result:
            assert len(result.getexif()) == 0

    def test_resizes_large_landscape(self, tmp_path: Path) -> None:
        raw = tmp_path / "in.jpg"
        out = tmp_path / "out.jpg"
        _write_jpeg(raw, 5000, 3000)

        w, h = process_photo_sync(raw, out)

        assert (w, h) == (_MAX_LONG_EDGE, 1800)
        with Image.open(out) as result:
            assert result.size == (_MAX_LONG_EDGE, 1800)

    def test_resizes_large_portrait(self, tmp_path: Path) -> None:
        raw = tmp_path / "in.jpg"
        out = tmp_path / "out.jpg"
        _write_jpeg(raw, 3000, 5000)

        w, h = process_photo_sync(raw, out)

        assert (w, h) == (1800, _MAX_LONG_EDGE)
        with Image.open(out) as result:
            assert result.size == (1800, _MAX_LONG_EDGE)

    def test_preserves_small_image(self, tmp_path: Path) -> None:
        raw = tmp_path / "in.jpg"
        out = tmp_path / "out.jpg"
        _write_jpeg(raw, 2000, 1500)

        w, h = process_photo_sync(raw, out)

        assert (w, h) == (2000, 1500)
        with Image.open(out) as result:
            assert result.size == (2000, 1500)

    def test_converts_png_to_jpeg(self, tmp_path: Path) -> None:
        raw = tmp_path / "in.png"
        out = tmp_path / "out.jpg"
        _write_png(raw, 800, 600)

        w, h = process_photo_sync(raw, out)

        assert (w, h) == (800, 600)
        with Image.open(out) as result:
            assert result.format == "JPEG"
            assert result.size == (800, 600)

    def test_handles_orientation_tag(self, tmp_path: Path) -> None:
        """EXIF orientation 6 (rotated 90 CW) should produce a transposed image."""
        img = Image.new("RGB", (400, 600))  # portrait source
        exif = img.getexif()
        exif[ExifBase.Orientation] = 6  # 90 CW rotation
        exif_bytes = exif.tobytes()

        raw = tmp_path / "in.jpg"
        out = tmp_path / "out.jpg"
        _write_jpeg(raw, 400, 600, exif=exif_bytes)

        w, h = process_photo_sync(raw, out)

        # After transpose: 600x400 (landscape)
        assert (w, h) == (600, 400)
        with Image.open(out) as result:
            assert result.size == (600, 400)


class TestProcessVideo:
    async def test_raises_when_output_hits_cap(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = tmp_path / "in.mp4"
        source.write_bytes(b"stub")
        out = tmp_path / "out.mp4"

        async def _fake_exec(*_args: object, **_kwargs: object) -> AsyncMock:
            out.write_bytes(b"x" * 2048)
            proc = AsyncMock()
            proc.communicate.return_value = (b"", b"")
            proc.returncode = 0
            return proc

        monkeypatch.setattr(
            "app.logic.media_upgrade.processing._MAX_OUTPUT_BYTES", 1024
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.processing._detect_hdr", lambda _: False
        )
        monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
        with pytest.raises(RuntimeError, match="cap"):
            await process_video(source, out)


# ---------------------------------------------------------------------------
# apply_upgrade_results
# ---------------------------------------------------------------------------


class TestApplyUpgradeResults:
    async def test_updates_media_for_succeeded_files(self, tmp_path: Path) -> None:
        """Succeeded files are re-probed and added to upgraded_media."""
        create_test_jpeg(tmp_path / "photo1.jpg", 4000, 3000)
        old_media = [Media(name="photo1.jpg", width=800, height=600)]
        matches = [MatchResult(local_name="photo1.jpg", google_id="gid-1", distance=0)]

        new_media, new_upgraded = await apply_upgrade_results(
            tmp_path,
            matches,
            old_media,
            {},
            {"photo1.jpg"},
        )
        assert len(new_media) == 1
        assert new_media[0].width == 4000
        assert new_media[0].height == 3000
        assert new_upgraded == {"photo1.jpg": "gid-1"}

    async def test_skips_files_not_in_succeeded(self, tmp_path: Path) -> None:
        """Files not in succeeded set keep original metadata."""
        create_test_jpeg(tmp_path / "photo1.jpg", 4000, 3000)
        old_media = [Media(name="photo1.jpg", width=800, height=600)]
        matches = [MatchResult(local_name="photo1.jpg", google_id="gid-1", distance=0)]

        new_media, new_upgraded = await apply_upgrade_results(
            tmp_path,
            matches,
            old_media,
            {},
            set(),
        )
        assert new_media[0].width == 800  # unchanged
        assert new_upgraded == {}

    async def test_skips_files_not_in_media_list(self, tmp_path: Path) -> None:
        """Files in succeeded but not in media list are silently skipped."""
        create_test_jpeg(tmp_path / "orphan.jpg", 4000, 3000)
        old_media = [Media(name="photo1.jpg", width=800, height=600)]
        matches = [MatchResult(local_name="orphan.jpg", google_id="gid-1", distance=0)]

        new_media, new_upgraded = await apply_upgrade_results(
            tmp_path,
            matches,
            old_media,
            {},
            {"orphan.jpg"},
        )
        assert len(new_media) == 1
        assert new_media[0].name == "photo1.jpg"
        assert new_upgraded == {}

    async def test_continues_on_probe_failure(self, tmp_path: Path) -> None:
        """If re-probing a file fails, it is skipped but others proceed."""
        create_test_jpeg(tmp_path / "good.jpg", 4000, 3000)
        # Write garbage to simulate a corrupted file
        (tmp_path / "bad.jpg").write_bytes(b"not an image")
        old_media = [
            Media(name="good.jpg", width=800, height=600),
            Media(name="bad.jpg", width=800, height=600),
        ]
        matches = [
            MatchResult(local_name="bad.jpg", google_id="gid-bad", distance=0),
            MatchResult(local_name="good.jpg", google_id="gid-good", distance=0),
        ]

        new_media, new_upgraded = await apply_upgrade_results(
            tmp_path,
            matches,
            old_media,
            {},
            {"bad.jpg", "good.jpg"},
        )
        assert new_upgraded == {"good.jpg": "gid-good"}
        media_by_name = {m.name: m for m in new_media}
        assert media_by_name["good.jpg"].width == 4000
        assert media_by_name["bad.jpg"].width == 800  # unchanged

    async def test_preserves_existing_upgraded_media(self, tmp_path: Path) -> None:
        """Previously upgraded files are preserved in the output map."""
        create_test_jpeg(tmp_path / "new.jpg", 4000, 3000)
        old_media = [
            Media(name="old.jpg", width=2000, height=1500),
            Media(name="new.jpg", width=800, height=600),
        ]
        matches = [MatchResult(local_name="new.jpg", google_id="gid-new", distance=0)]
        existing_upgraded = {"old.jpg": "gid-old"}

        _, new_upgraded = await apply_upgrade_results(
            tmp_path,
            matches,
            old_media,
            existing_upgraded,
            {"new.jpg"},
        )
        assert new_upgraded == {"old.jpg": "gid-old", "new.jpg": "gid-new"}

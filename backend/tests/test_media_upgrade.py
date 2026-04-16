"""Unit tests for media matching and processing.

Tests pure computation: time-window bucketing, distance matrix building,
Hungarian matching, threshold rejection, cross-step fallback, video frame
extraction, and post-download photo processing (EXIF strip, resize,
format conversion).
"""

import json
import subprocess
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import imagehash
import numpy as np
import pytest
from PIL import Image
from PIL.ExifTags import Base as ExifBase

from app.logic.media_upgrade import (
    _FALLBACK_MAX_DIMENSION,
    _MAX_LONG_EDGE,
    MATCH_THRESHOLD,
    MatchResult,
    _bucket_by_window,
    _cross_step_fallback,
    _extract_video_frames,
    _parse_timestamp,
    _process_photo_sync,
    _process_video,
    build_cost_matrix,
    build_step_windows,
    match_within_window,
)
from app.services.google_photos import MediaFile, PickedMediaItem


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
            local_is_video=[False],
            candidate_is_video=[False],
        )
        assert matrix[0][0] == 0

    def test_completely_different_hashes_produce_high_cost(self) -> None:
        h1 = _make_hash(0x0)
        h2 = _make_hash(0xFFFFFFFFFFFFFFFF)
        matrix = build_cost_matrix(
            local_hashes=[h1],
            candidate_hashes=[h2],
            local_is_video=[False],
            candidate_is_video=[False],
        )
        assert matrix[0][0] == 64  # all bits differ

    def test_matrix_shape_matches_inputs(self) -> None:
        hashes = [_make_hash(i) for i in range(3)]
        candidates = [_make_hash(i + 100) for i in range(5)]
        matrix = build_cost_matrix(
            hashes,
            candidates,
            local_is_video=[False] * 3,
            candidate_is_video=[False] * 5,
        )
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
            local_is_video=[False, False],
            candidate_is_video=[False, False],
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
            local_is_video=[False],
            candidate_is_video=[False],
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
            local_is_video=[False, False],
            candidate_is_video=[False, False],
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
            local_is_video=[],
            candidate_is_video=[False],
        )
        assert results == []

    def test_more_candidates_than_locals(self) -> None:
        h = _make_hash(42)
        results = match_within_window(
            local_names=["photo1.jpg"],
            local_hashes=[h],
            candidate_ids=["gp-1", "gp-2", "gp-3"],
            candidate_hashes=[_make_hash(99), h, _make_hash(88)],
            local_is_video=[False],
            candidate_is_video=[False, False, False],
        )
        assert len(results) == 1
        assert results[0].google_id == "gp-2"
        assert results[0].distance == 0


class TestMediaAwareCostMatrix:
    def test_single_hash_unchanged(self) -> None:
        """Photo-to-photo matching works as before."""
        h = _make_hash(0xFF00FF00FF00FF00)
        matrix = build_cost_matrix(
            local_hashes=[h],
            candidate_hashes=[h],
            local_is_video=[False],
            candidate_is_video=[False],
        )
        assert matrix[0][0] == 0

    def test_video_uses_minimum_distance(self) -> None:
        """Video cost is min distance across sampled frames."""
        h_close = _make_hash(42)
        h_far = _make_hash(0xFFFFFFFFFFFFFFFF)
        h_candidate = _make_hash(42)
        matrix = build_cost_matrix(
            local_hashes=[[h_far, h_close, h_far, h_far]],
            candidate_hashes=[h_candidate],
            local_is_video=[True],
            candidate_is_video=[True],
        )
        assert matrix[0][0] == 0  # min of distances, h_close matches exactly

    def test_cross_type_gets_infinite_cost(self) -> None:
        """Photo-to-video pairs get cost above threshold."""
        h = _make_hash(42)
        matrix = build_cost_matrix(
            local_hashes=[h],
            candidate_hashes=[h],
            local_is_video=[False],
            candidate_is_video=[True],
        )
        assert matrix[0][0] > MATCH_THRESHOLD

    def test_video_to_photo_gets_infinite_cost(self) -> None:
        h = _make_hash(42)
        matrix = build_cost_matrix(
            local_hashes=[[h, h, h, h]],
            candidate_hashes=[h],
            local_is_video=[True],
            candidate_is_video=[False],
        )
        assert matrix[0][0] > MATCH_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers for bucketing / fallback tests
# ---------------------------------------------------------------------------


def _make_item(
    item_id: str,
    create_time: str,
    *,
    item_type: str = "PHOTO",
    video_processing_status: str | None = None,
) -> PickedMediaItem:
    return PickedMediaItem(
        id=item_id,
        create_time=create_time,
        type=item_type,
        media_file=MediaFile(
            base_url="https://example.com",
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
        bucketed = _bucket_by_window([item], windows)
        assert len(bucketed[1]) == 1
        assert bucketed[1][0].id == "g1"

    def test_video_without_status_accepted(self) -> None:
        """Videos with no processing status (None) are accepted."""
        windows = build_step_windows(
            step_timestamps=[1_000_000.0],
            step_ids=[1],
        )
        video = _make_item("v1", "1970-01-12T13:46:40+00:00", item_type="VIDEO")
        bucketed = _bucket_by_window([video], windows)
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
        bucketed = _bucket_by_window([video], windows)
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
        bucketed = _bucket_by_window([video], windows)
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
        bucketed = _bucket_by_window([video], windows)
        assert len(bucketed[1]) == 0

    def test_invalid_timestamp_skipped(self) -> None:
        windows = build_step_windows(
            step_timestamps=[1_000_000.0],
            step_ids=[1],
        )
        bad = _make_item("b1", "not-a-timestamp")
        bucketed = _bucket_by_window([bad], windows)
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
        bucketed = _bucket_by_window([item], windows)
        # Should land in window 1 (via overlap) and also window 2
        assert any(i.id == "g1" for i in bucketed[1])


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

        _cross_step_fallback(
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

        _cross_step_fallback(
            all_matches,
            matched_locals,
            matched_candidates,
            media_names=["photo1.jpg"],
            local_hashes={"photo1.jpg": h},
            candidate_hashes={"gp-1": h},
            google_items=[_make_item("gp-1", "2024-01-15T10:00:00Z")],
        )

        assert len(all_matches) == 0

    def test_skips_when_exceeding_dimension_limit(self) -> None:
        """Fallback is skipped when matrix would be too large."""
        h = _make_hash(0)
        n = _FALLBACK_MAX_DIMENSION + 1
        names = [f"photo{i}.jpg" for i in range(n)]
        hashes = dict.fromkeys(names, h)
        items = [_make_item(f"gp-{i}", "2024-01-15T10:00:00Z") for i in range(n)]
        candidate_hashes = {f"gp-{i}": h for i in range(n)}

        all_matches: list[MatchResult] = []
        _cross_step_fallback(
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


def _make_jpeg_bytes(width: int, height: int, *, exif: bytes | None = None) -> bytes:
    """Create a JPEG image in memory, optionally with EXIF data."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = BytesIO()
    kwargs: dict = {"format": "JPEG", "quality": 95}
    if exif is not None:
        kwargs["exif"] = exif
    img.save(buf, **kwargs)
    return buf.getvalue()


def _make_png_bytes(width: int, height: int) -> bytes:
    """Create a PNG image in memory."""
    img = Image.new("RGBA", (width, height), color=(100, 150, 200, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestProcessPhoto:
    def test_strips_exif(self) -> None:
        """EXIF metadata must be removed."""
        img = Image.new("RGB", (800, 600))
        exif = img.getexif()
        exif[ExifBase.Make] = "TestCamera"
        exif[ExifBase.Model] = "X100"
        exif[ExifBase.Software] = "TestSuite"
        exif_bytes = exif.tobytes()

        data = _make_jpeg_bytes(800, 600, exif=exif_bytes)

        # Verify source has EXIF
        with Image.open(BytesIO(data)) as src:
            assert len(src.getexif()) > 0

        result = _process_photo_sync(data)

        with Image.open(BytesIO(result)) as out:
            assert len(out.getexif()) == 0

    def test_resizes_large_landscape(self) -> None:
        data = _make_jpeg_bytes(5000, 3000)
        result = _process_photo_sync(data)

        with Image.open(BytesIO(result)) as out:
            assert out.size == (_MAX_LONG_EDGE, 1800)

    def test_resizes_large_portrait(self) -> None:
        data = _make_jpeg_bytes(3000, 5000)
        result = _process_photo_sync(data)

        with Image.open(BytesIO(result)) as out:
            assert out.size == (1800, _MAX_LONG_EDGE)

    def test_preserves_small_image(self) -> None:
        data = _make_jpeg_bytes(2000, 1500)
        result = _process_photo_sync(data)

        with Image.open(BytesIO(result)) as out:
            assert out.size == (2000, 1500)

    def test_converts_png_to_jpeg(self) -> None:
        data = _make_png_bytes(800, 600)
        result = _process_photo_sync(data)

        with Image.open(BytesIO(result)) as out:
            assert out.format == "JPEG"
            assert out.size == (800, 600)

    def test_handles_orientation_tag(self) -> None:
        """EXIF orientation 6 (rotated 90 CW) should produce a transposed image."""
        img = Image.new("RGB", (400, 600))  # portrait source
        exif = img.getexif()
        exif[ExifBase.Orientation] = 6  # 90 CW rotation
        exif_bytes = exif.tobytes()

        data = _make_jpeg_bytes(400, 600, exif=exif_bytes)
        result = _process_photo_sync(data)

        with Image.open(BytesIO(result)) as out:
            # After transpose: 600x400 (landscape)
            assert out.size == (600, 400)


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """Create a minimal 2-second test video via ffmpeg."""
    out = tmp_path / "test.mp4"
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:size=320x240:duration=2:rate=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


class TestExtractVideoFrames:
    def test_extracts_four_frames(self, sample_video: Path) -> None:
        frames = _extract_video_frames(sample_video)
        assert len(frames) == 4
        for frame in frames:
            assert isinstance(frame, imagehash.ImageHash)

    def test_all_frames_from_same_video_are_similar(self, sample_video: Path) -> None:
        """A solid-color video should produce near-identical hashes."""
        frames = _extract_video_frames(sample_video)
        for i in range(len(frames) - 1):
            assert frames[i] - frames[i + 1] < 5


class TestProcessVideo:
    async def test_reencodes_to_h264(self, sample_video: Path, tmp_path: Path) -> None:
        data = sample_video.read_bytes()  # noqa: ASYNC240
        out = tmp_path / "out.mp4"
        await _process_video(data, out)

        assert out.exists()
        # Verify H.264 codec via ffprobe
        result = subprocess.run(  # noqa: S603, ASYNC221
            [  # noqa: S607
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "csv=p=0",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.stdout.strip() == "h264"

    async def test_caps_resolution(self, tmp_path: Path) -> None:
        # Create a 4K test video
        source = tmp_path / "4k.mp4"
        subprocess.run(  # noqa: S603, ASYNC221
            [  # noqa: S607
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:size=3840x2160:duration=1:rate=30",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(source),
            ],
            check=True,
            capture_output=True,
        )
        data = source.read_bytes()
        out = tmp_path / "out.mp4"
        await _process_video(data, out)

        # Check output dimensions
        result = subprocess.run(  # noqa: S603, ASYNC221
            [  # noqa: S607
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        w, h = (int(x) for x in result.stdout.strip().split(","))
        assert max(w, h) <= _MAX_LONG_EDGE

    async def test_strips_metadata(self, sample_video: Path, tmp_path: Path) -> None:
        data = sample_video.read_bytes()  # noqa: ASYNC240
        out = tmp_path / "out.mp4"
        await _process_video(data, out)

        result = subprocess.run(  # noqa: S603, ASYNC221
            [  # noqa: S607
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format_tags",
                "-of",
                "json",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        tags = json.loads(result.stdout).get("format", {}).get("tags", {})
        # Should have no meaningful metadata (ffmpeg adds encoder tag, that's ok)
        assert "location" not in tags
        assert "creation_time" not in tags

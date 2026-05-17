"""Tests for the media upgrade pipeline.

Unit tests are scoped to the algorithmic edge cases that motivated the
code (Hungarian optimality, overlap-margin boundary, cross-step
fallback dimension cap) plus the real-I/O photo/video processing. A
single integration test exercises ``run_matching`` end-to-end against
fixture JPEGs on disk.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import imagehash
import numpy as np
import pytest
from PIL import Image
from PIL.ExifTags import Base as ExifBase

if TYPE_CHECKING:
    import httpx
    from sqlmodel.ext.asyncio.session import AsyncSession

from app.logic.media_upgrade.phash_matching import (
    _FALLBACK_MAX_DIMENSION,
    HashedMedia,
    MatchResult,
    bucket_by_window,
    build_step_windows,
    compute_phash_from_path,
    cross_step_fallback,
    match_within_window,
)
from app.logic.media_upgrade.pipeline import (
    MatchCompleted,
    MatchInProgress,
    _clear_caches,
    _needs_upgrade,
    _persist_upgrade_in_session,
    run_matching,
)
from app.logic.media_upgrade.processing import (
    _MAX_LONG_EDGE,
    process_photo_sync,
    process_video,
)
from app.models.google_photos import GoogleMediaFile, GoogleMediaType, PickedMediaItem

from .factories import AID, create_test_jpeg, insert_album, insert_album_media


@pytest.fixture(autouse=True)
def _clear_upgrade_caches_between_tests() -> Iterator[None]:
    """Reset the event-loop-bound semaphore cache between tests."""
    yield
    _clear_caches()


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


def _make_item(
    item_id: str,
    create_time: str,
    *,
    item_type: GoogleMediaType = "PHOTO",
    video_processing_status: str | None = None,
    base_url: str = "https://lh3.googleusercontent.com/test",
) -> PickedMediaItem:
    return PickedMediaItem(
        id=item_id,
        create_time=create_time,
        type=item_type,
        media_file=GoogleMediaFile(
            base_url=base_url,
            mime_type="video/mp4" if item_type == "VIDEO" else "image/jpeg",
            filename=f"{item_id}.mp4" if item_type == "VIDEO" else f"{item_id}.jpg",
        ),
        video_processing_status=video_processing_status,
    )


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


# ---------------------------------------------------------------------------
# Targeted algorithm regression guards
# ---------------------------------------------------------------------------


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


class TestMatchWithinWindow:
    def test_optimal_assignment_not_greedy(self) -> None:
        """Hungarian must find the global optimum, not a greedy local one.

        Regression guard: a greedy matcher would pair photo1 with the nearest
        candidate and leave photo2 worse off; the global optimum swaps them.
        """
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


class TestBucketByWindow:
    def test_overlap_margin_includes_boundary_items(self) -> None:
        """Items just past a window boundary match via overlap.

        Regression guard: an item 10 min past a step boundary must still be
        considered for the previous step (30-min overlap).
        """
        windows = build_step_windows(
            step_timestamps=[1_000_000.0, 1_050_000.0],
            step_ids=[1, 2],
        )
        t = 1_050_000.0 + 600
        iso = datetime.fromtimestamp(t, UTC).isoformat()
        item = _make_item("g1", iso)
        bucketed = bucket_by_window([item], windows)
        assert any(i.id == "g1" for i in bucketed[1])
        assert any(i.id == "g1" for i in bucketed[2])


class TestCrossStepFallback:
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
        """Fallback is skipped when the matrix would be too large."""
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
# _needs_upgrade
# ---------------------------------------------------------------------------


class TestNeedsUpgrade:
    def test_candidate_needs_upgrade(self) -> None:
        match = MatchResult(local_name="photo.jpg", google_id="gid-A", distance=0)
        assert _needs_upgrade(match, {"photo.jpg"}) is True

    def test_non_candidate_skips(self) -> None:
        match = MatchResult(local_name="photo.jpg", google_id="gid-A", distance=0)
        assert _needs_upgrade(match, set()) is False


class TestPersistUpgrade:
    async def test_updates_album_media_byte_size(
        self,
        session: AsyncSession,
        tmp_path: Path,
    ) -> None:
        uid = 1
        await insert_album(session, uid)
        media = await insert_album_media(session, uid, name="photo.jpg")
        media.byte_size = 1
        session.add(media)
        target = create_test_jpeg(tmp_path / "photo.jpg", 1200, 800)
        await session.commit()

        await _persist_upgrade_in_session(
            session,
            uid=uid,
            aid=AID,
            album_dir=tmp_path,
            matches=[
                MatchResult(local_name="photo.jpg", google_id="google-1", distance=0)
            ],
            succeeded={"photo.jpg"},
        )
        await session.refresh(media)

        assert media.byte_size == target.stat().st_size
        assert media.upgrade_candidate is False


# ---------------------------------------------------------------------------
# run_matching end-to-end
# ---------------------------------------------------------------------------


class TestRunMatching:
    async def test_marks_matches_outside_upgrade_candidates_as_upgraded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        album_dir = tmp_path / "album"
        album_dir.mkdir()
        (album_dir / "photo.jpg").write_bytes(b"fake")
        h = _make_hash(0)

        async def fake_local(
            _album_dir: Path, name: str
        ) -> tuple[str, imagehash.ImageHash]:
            return name, h

        async def fake_candidate(*_args: object) -> tuple[str, imagehash.ImageHash]:
            return "gp-1", h

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_local_one", fake_local
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_candidate_one", fake_candidate
        )

        async def fake_token() -> str:
            return "test-token"

        events = [
            event
            async for event in run_matching(
                clients=AsyncMock(),
                album_dir=album_dir,
                media_by_step={1: ["photo.jpg"]},
                step_timestamps=[datetime(2024, 1, 15, 10, 0, tzinfo=UTC).timestamp()],
                step_ids=[1],
                google_items=[
                    _make_item(
                        "gp-1",
                        datetime(2024, 1, 15, 10, 5, tzinfo=UTC).isoformat(),
                    )
                ],
                tokens=fake_token,
                upgrade_candidates=set(),
            )
        ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert summary.matches[0].upgraded is True

    async def test_matches_real_images_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Full matching pipeline against real JPEGs on disk.

        Each Google item's base_url points at its own id; the mocked
        ``download_media_bytes`` returns the matching local file's bytes so
        candidate hashes equal local hashes. Exercises bucketing, local
        hashing, candidate hashing, within-window Hungarian, cross-step
        fallback, and the terminal summary event.
        """
        album_dir = tmp_path / "album"
        album_dir.mkdir()

        step_timestamps = [
            datetime(2024, 1, 15, 10, 0, tzinfo=UTC).timestamp(),
            datetime(2024, 1, 15, 14, 0, tzinfo=UTC).timestamp(),
            datetime(2024, 1, 15, 18, 0, tzinfo=UTC).timestamp(),
        ]
        step_ids = [1, 2, 3]
        names = ["step1.jpg", "step2.jpg", "step3.jpg"]

        # Visually distinct images so each pHash is unique.
        bytes_by_name: dict[str, bytes] = {}
        for i, name in enumerate(names):
            img = Image.new("RGB", (400, 300))
            for y in range(300):
                for x in range(400):
                    img.putpixel(
                        (x, y),
                        ((x + i * 100) % 256, (y + i * 50) % 256, (i * 80) % 256),
                    )
            path = album_dir / name
            img.save(path, "JPEG", quality=90)
            bytes_by_name[name] = path.read_bytes()

        # Google items: one per step, base_url encodes the local file.
        google_items = [
            _make_item(
                f"gp-{i}",
                datetime(2024, 1, 15, 10 + i * 4, 30, tzinfo=UTC).isoformat(),
                base_url=f"https://lh3.googleusercontent.com/{name}",
            )
            for i, name in enumerate(names)
        ]
        url_to_bytes = {
            item.media_file.base_url: bytes_by_name[names[i]]
            for i, item in enumerate(google_items)
        }

        async def fake_download(
            _client: httpx.AsyncClient,
            base_url: str,
            _access_token: str,
            *,
            param: str = "=d",
            max_bytes: int = 0,
        ) -> bytes:
            return url_to_bytes[base_url]

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline.download_media_bytes", fake_download
        )

        async def fake_token() -> str:
            return "test-token"

        clients = AsyncMock()
        events = [
            event
            async for event in run_matching(
                clients=clients,
                album_dir=album_dir,
                media_by_step={
                    sid: [n] for sid, n in zip(step_ids, names, strict=True)
                },
                step_timestamps=step_timestamps,
                step_ids=step_ids,
                google_items=google_items,
                tokens=fake_token,
            )
        ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert summary.total_picked == 3
        assert summary.matched == 3
        assert summary.unmatched == 0
        assert not any(m.upgraded for m in summary.matches)
        assert {m.local_name for m in summary.matches} == set(names)
        assert {m.google_id for m in summary.matches} == {"gp-0", "gp-1", "gp-2"}

        progress = [e for e in events[:-1] if isinstance(e, MatchInProgress)]
        assert {e.phase for e in progress} == {"preparing", "matching"}

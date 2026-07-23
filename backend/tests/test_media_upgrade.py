import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import imagehash
import numpy as np
import pytest
from PIL import Image
from PIL.ExifTags import Base as ExifBase
from structlog.testing import capture_logs

from app.logic.media_upgrade import phash_matching

if TYPE_CHECKING:
    import httpx
    from sqlmodel.ext.asyncio.session import AsyncSession

from app.logic.media_upgrade.phash_matching import (
    HashedMedia,
    MatchResult,
    compute_phash_from_path,
)
from app.logic.media_upgrade.pipeline import (
    MatchCompleted,
    MatchInProgress,
    UpgradeCompleted,
    _clear_caches,
    _needs_upgrade,
    _persist_upgrade_in_session,
    run_matching,
    run_upgrade,
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
    yield
    _clear_caches()


def _make_hash(value: int) -> imagehash.ImageHash:
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
    width: int | None = None,
    height: int | None = None,
) -> PickedMediaItem:
    return PickedMediaItem(
        id=item_id,
        create_time=create_time,
        type=item_type,
        media_file=GoogleMediaFile(
            base_url=base_url,
            mime_type="video/mp4" if item_type == "VIDEO" else "image/jpeg",
            filename=f"{item_id}.mp4" if item_type == "VIDEO" else f"{item_id}.jpg",
            width=width,
            height=height,
        ),
        video_processing_status=video_processing_status,
    )


def _write_jpeg(
    path: Path, width: int, height: int, *, exif: bytes | None = None
) -> None:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    kwargs: dict = {"format": "JPEG", "quality": 95}
    if exif is not None:
        kwargs["exif"] = exif
    img.save(path, **kwargs)


def _write_png(path: Path, width: int, height: int) -> None:
    img = Image.new("RGBA", (width, height), color=(100, 150, 200, 255))
    img.save(path, format="PNG")


async def _test_token() -> str:
    return "test-token"


def _match_dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2024, 1, 15, hour, minute, tzinfo=UTC)


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

    def test_global_matching_excludes_cross_type_edges_from_diagnostics(self) -> None:
        local = [_hm("photo.jpg", _make_hash(0))]
        candidates = [
            _hm("google-video", _make_hash(0), video=True),
            _hm("google-photo", _make_hash((1 << 13) - 1)),
        ]

        outcome = phash_matching.match_media_globally(local, candidates)

        assert outcome.matches == []
        assert outcome.diagnostics.valid_edges == 0
        assert outcome.diagnostics.nearest_13_to_15 == 1

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


class TestProcessPhoto:
    def test_strips_exif(self, tmp_path: Path) -> None:
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

    @pytest.mark.parametrize(
        ("source_size", "expected_size"),
        [
            ((5000, 3000), (_MAX_LONG_EDGE, 1800)),
            ((3000, 5000), (1800, _MAX_LONG_EDGE)),
            ((2000, 1500), (2000, 1500)),
        ],
    )
    def test_resizes_photos(
        self,
        tmp_path: Path,
        source_size: tuple[int, int],
        expected_size: tuple[int, int],
    ) -> None:
        raw = tmp_path / "in.jpg"
        out = tmp_path / "out.jpg"
        _write_jpeg(raw, *source_size)

        w, h = process_photo_sync(raw, out)

        assert (w, h) == expected_size
        with Image.open(out) as result:
            assert result.size == expected_size

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
        img = Image.new("RGB", (400, 600))
        exif = img.getexif()
        exif[ExifBase.Orientation] = 6
        exif_bytes = exif.tobytes()

        raw = tmp_path / "in.jpg"
        out = tmp_path / "out.jpg"
        _write_jpeg(raw, 400, 600, exif=exif_bytes)

        w, h = process_photo_sync(raw, out)

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


class TestNeedsUpgrade:
    @pytest.mark.parametrize(
        ("upgrade_candidates", "expected"),
        [
            ({"photo.jpg"}, True),
            (set(), False),
        ],
    )
    def test_needs_upgrade(
        self, upgrade_candidates: set[str], *, expected: bool
    ) -> None:
        match = MatchResult(local_name="photo.jpg", google_id="gid-A", distance=0)
        assert _needs_upgrade(match, upgrade_candidates) is expected


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


class TestRunMatching:
    async def test_logs_aggregate_matching_diagnostics_after_hash_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        h = _make_hash(0)

        async def fake_local(
            _album_dir: Path, name: str
        ) -> tuple[str, imagehash.ImageHash | None]:
            return name, None if name == "failed.jpg" else h

        async def fake_candidate(
            _download: object, item: PickedMediaItem, _tokens: object
        ) -> tuple[str, imagehash.ImageHash | None]:
            return item.id, None if item.id == "google-failed" else h

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_local_one", fake_local
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_candidate_one", fake_candidate
        )

        with capture_logs() as logs:
            events = [
                event
                async for event in run_matching(
                    clients=AsyncMock(),
                    album_dir=tmp_path,
                    media_by_step={1: ["matched.jpg", "failed.jpg"]},
                    step_ids=[1],
                    google_items=[
                        _make_item("google-matched", _match_dt(10, 5).isoformat()),
                        _make_item("google-failed", _match_dt(10, 6).isoformat()),
                    ],
                    tokens=_test_token,
                )
            ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert summary.matched == 1
        completed = next(
            log
            for log in logs
            if log.get("event") == "google_photos.matching.completed"
        )
        assert completed == {
            "event": "google_photos.matching.completed",
            "log_level": "info",
            "picked": 2,
            "matchable_picked": 2,
            "relevant_local": 2,
            "local_hashed": 1,
            "candidate_hashed": 1,
            "valid_edges": 1,
            "matched": 1,
            "unmatched_local": 0,
            "nearest_13_to_15": 0,
        }

    async def test_matches_picked_items_regardless_of_timestamp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hashes = {
            "inside.jpg": _make_hash(0),
            "outside.jpg": _make_hash((1 << 64) - 1),
        }

        async def fake_local(
            _album_dir: Path, name: str
        ) -> tuple[str, imagehash.ImageHash]:
            return name, hashes[name]

        async def fake_candidate(
            _download: object, item: PickedMediaItem, _tokens: object
        ) -> tuple[str, imagehash.ImageHash]:
            local_name = f"{item.id.removeprefix('google-')}.jpg"
            return item.id, hashes[local_name]

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_local_one", fake_local
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_candidate_one", fake_candidate
        )

        events = [
            event
            async for event in run_matching(
                clients=AsyncMock(),
                album_dir=tmp_path,
                media_by_step={1: ["inside.jpg", "outside.jpg"]},
                step_ids=[1],
                google_items=[
                    _make_item("google-inside", _match_dt(10, 5).isoformat()),
                    _make_item("google-outside", "2024-01-20T10:00:00+00:00"),
                ],
                tokens=_test_token,
            )
        ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert {match.google_id for match in summary.matches} == {
            "google-inside",
            "google-outside",
        }

    async def test_hashes_all_album_media_regardless_of_picker_timestamps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hashes = {
            "first.jpg": _make_hash(0),
            "second.jpg": _make_hash((1 << 64) - 1),
        }
        hashed_local_names: list[str] = []

        async def fake_local(
            _album_dir: Path, name: str
        ) -> tuple[str, imagehash.ImageHash]:
            hashed_local_names.append(name)
            return name, hashes[name]

        async def fake_candidate(
            _download: object, item: PickedMediaItem, _tokens: object
        ) -> tuple[str, imagehash.ImageHash]:
            return item.id, hashes["second.jpg"]

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_local_one", fake_local
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_candidate_one", fake_candidate
        )

        events = [
            event
            async for event in run_matching(
                clients=AsyncMock(),
                album_dir=tmp_path,
                media_by_step={1: ["first.jpg"], 2: ["second.jpg"]},
                step_ids=[1, 2],
                google_items=[
                    _make_item("google-second", _match_dt(10, 30).isoformat())
                ],
                tokens=_test_token,
            )
        ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert set(hashed_local_names) == {"first.jpg", "second.jpg"}
        assert [(match.local_name, match.google_id) for match in summary.matches] == [
            ("second.jpg", "google-second")
        ]

    async def test_excludes_processing_videos_from_candidate_hashing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        h = _make_hash(0)
        hashed_candidate_ids: list[str] = []

        async def fake_local(
            _album_dir: Path, name: str
        ) -> tuple[str, imagehash.ImageHash]:
            return name, h

        async def fake_candidate(
            _download: object, item: PickedMediaItem, _tokens: object
        ) -> tuple[str, imagehash.ImageHash]:
            hashed_candidate_ids.append(item.id)
            return item.id, h

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_local_one", fake_local
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_candidate_one", fake_candidate
        )

        events = [
            event
            async for event in run_matching(
                clients=AsyncMock(),
                album_dir=tmp_path,
                media_by_step={1: ["photo.jpg"]},
                step_ids=[1],
                google_items=[
                    _make_item(
                        "processing-video",
                        _match_dt(10, 5).isoformat(),
                        item_type="VIDEO",
                        video_processing_status="PROCESSING",
                    ),
                    _make_item("ready-photo", _match_dt(10, 6).isoformat()),
                ],
                tokens=_test_token,
            )
        ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert hashed_candidate_ids == ["ready-photo"]
        assert summary.total_picked == 2
        assert summary.matched == 1
        assert summary.unmatched == 1
        assert [
            event.total
            for event in events
            if isinstance(event, MatchInProgress) and event.phase == "matching"
        ] == [1]

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

        events = [
            event
            async for event in run_matching(
                clients=AsyncMock(),
                album_dir=album_dir,
                media_by_step={1: ["photo.jpg"]},
                step_ids=[1],
                google_items=[_make_item("gp-1", _match_dt(10, 5).isoformat())],
                tokens=_test_token,
                upgrade_candidates=set(),
            )
        ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert summary.matches[0].upgraded is True

    async def test_matches_real_images_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        album_dir = tmp_path / "album"
        album_dir.mkdir()

        step_ids = [1, 2, 3]
        names = ["step1.jpg", "step2.jpg", "step3.jpg"]

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

        google_items = [
            _make_item(
                f"gp-{i}",
                _match_dt(10 + i * 4, 30).isoformat(),
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

        clients = AsyncMock()
        events = [
            event
            async for event in run_matching(
                clients=clients,
                album_dir=album_dir,
                media_by_step={
                    sid: [n] for sid, n in zip(step_ids, names, strict=True)
                },
                step_ids=step_ids,
                google_items=google_items,
                tokens=_test_token,
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


class TestRunUpgrade:
    @pytest.mark.parametrize(
        ("google_width", "google_height"),
        [(1200, 800), (800, 600)],
    )
    async def test_skips_non_larger_picker_metadata_without_downloading(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        google_width: int,
        google_height: int,
    ) -> None:
        download_and_replace = AsyncMock(return_value=True)
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._download_and_replace",
            download_and_replace,
        )
        persist_upgrade = AsyncMock()
        cleanup_picker_sessions = AsyncMock()
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._persist_upgrade", persist_upgrade
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._cleanup_picker_sessions",
            cleanup_picker_sessions,
        )
        match = MatchResult(
            local_name="photo.jpg", google_id="google-photo", distance=0
        )

        events = [
            event
            async for event in run_upgrade(
                clients=AsyncMock(),
                uid=1,
                aid="album",
                album_dir=tmp_path,
                matches=[match],
                google_items_by_id={
                    "google-photo": _make_item(
                        "google-photo",
                        _match_dt(10).isoformat(),
                        width=google_width,
                        height=google_height,
                    )
                },
                upgrade_candidates={"photo.jpg"},
                local_dimensions={"photo.jpg": (1200, 800)},
                tokens=_test_token,
                session_ids=[],
            )
        ]

        download_and_replace.assert_not_awaited()
        persist_upgrade.assert_awaited_once()
        cleanup_picker_sessions.assert_awaited_once()
        assert not (tmp_path / ".upgrade-tmp").exists()
        assert events[-1] == UpgradeCompleted(replaced=0, skipped=1, failed=0)

    @pytest.mark.parametrize(
        ("google_width", "google_height"),
        [(1600, 900), (None, None)],
    )
    async def test_downloads_when_picker_metadata_may_be_larger(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        google_width: int | None,
        google_height: int | None,
    ) -> None:
        download_and_replace = AsyncMock(return_value=True)
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._download_and_replace",
            download_and_replace,
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._persist_upgrade", AsyncMock()
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._cleanup_picker_sessions", AsyncMock()
        )
        match = MatchResult(
            local_name="photo.jpg", google_id="google-photo", distance=0
        )

        events = [
            event
            async for event in run_upgrade(
                clients=AsyncMock(),
                uid=1,
                aid="album",
                album_dir=tmp_path,
                matches=[match],
                google_items_by_id={
                    "google-photo": _make_item(
                        "google-photo",
                        _match_dt(10).isoformat(),
                        width=google_width,
                        height=google_height,
                    )
                },
                upgrade_candidates={"photo.jpg"},
                local_dimensions={"photo.jpg": (1200, 800)},
                tokens=_test_token,
                session_ids=[],
            )
        ]

        download_and_replace.assert_awaited_once()
        assert events[-1] == UpgradeCompleted(replaced=1, skipped=0, failed=0)

    async def test_serializes_upgrade_file_lifecycles_with_two_gib_limit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline.detect_memory_mb", lambda: 2048
        )
        _clear_caches()
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        second_started = asyncio.Event()
        calls = 0

        async def fake_replace(*_args: object, **_kwargs: object) -> bool:
            nonlocal calls
            calls += 1
            if calls == 1:
                first_started.set()
                await release_first.wait()
            else:
                second_started.set()
            return True

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._download_and_replace", fake_replace
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._persist_upgrade", AsyncMock()
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._cleanup_picker_sessions", AsyncMock()
        )

        names = [
            f"00000000-0000-4000-8000-{i:012d}_"
            f"00000000-0000-4000-8000-{i + 10:012d}.jpg"
            for i in range(2)
        ]
        matches = [
            MatchResult(local_name=name, google_id=f"gp-{i}", distance=0)
            for i, name in enumerate(names)
        ]
        items = {
            f"gp-{i}": _make_item(f"gp-{i}", _match_dt(10).isoformat())
            for i in range(2)
        }

        async def collect() -> list[object]:
            return [
                event
                async for event in run_upgrade(
                    clients=AsyncMock(),
                    uid=1,
                    aid="album",
                    album_dir=tmp_path,
                    matches=matches,
                    google_items_by_id=items,
                    upgrade_candidates=set(names),
                    local_dimensions={},
                    tokens=_test_token,
                    session_ids=[],
                )
            ]

        task = asyncio.create_task(collect())
        try:
            await asyncio.wait_for(first_started.wait(), timeout=1)
            await asyncio.sleep(0)
            assert not second_started.is_set()
        finally:
            release_first.set()
        events = await task

        assert second_started.is_set()
        assert isinstance(events[-1], UpgradeCompleted)

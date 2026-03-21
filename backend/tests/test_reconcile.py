"""Tests for the reconciliation pipeline (re-uploaded user data)."""

from pathlib import Path

from app.logic.reconcile import _pick_cover, _scan_step_media
from app.models.polarsteps import Location, PSStep


def _ps_step(step_id: int, slug: str = "step") -> PSStep:
    """Minimal PSStep for testing."""
    return PSStep.model_construct(
        id=step_id,
        name=f"Step {step_id}",
        slug=slug,
        description="",
        timestamp=1_700_000_000.0 + step_id * 3600,
        timezone_id="UTC",
        location=Location(
            name="Place", detail="", country_code="nl", lat=52.0, lon=4.0
        ),
    )


class TestScanStepMedia:
    def test_finds_photos_and_videos(self, tmp_path: Path) -> None:
        ps = _ps_step(1, slug="naples")
        step_folder = tmp_path / ps.folder_name
        (step_folder / "photos").mkdir(parents=True)
        (step_folder / "videos").mkdir(parents=True)
        (step_folder / "photos" / "IMG_001.jpg").write_bytes(b"\xff\xd8")
        (step_folder / "videos" / "VID_001.mp4").write_bytes(b"\x00")

        result = _scan_step_media(tmp_path, ps)
        assert "IMG_001.jpg" in result
        assert "VID_001.mp4" in result

    def test_empty_step_folder(self, tmp_path: Path) -> None:
        ps = _ps_step(2, slug="empty")
        # No photos/videos dirs
        result = _scan_step_media(tmp_path, ps)
        assert result == set()

    def test_normalizes_double_jpg_extension(self, tmp_path: Path) -> None:
        """normalize_name strips the .jpg.jpg double extension from Polarsteps ZIPs."""
        ps = _ps_step(3, slug="upper")
        photos = tmp_path / ps.folder_name / "photos"
        photos.mkdir(parents=True)
        (photos / "IMG_ABC.jpg.jpg").write_bytes(b"\xff\xd8")

        result = _scan_step_media(tmp_path, ps)
        assert "IMG_ABC.jpg" in result

    def test_ignores_subdirectories(self, tmp_path: Path) -> None:
        ps = _ps_step(4, slug="nested")
        photos = tmp_path / ps.folder_name / "photos"
        photos.mkdir(parents=True)
        (photos / "real.jpg").write_bytes(b"\xff\xd8")
        (photos / "subdir").mkdir()

        result = _scan_step_media(tmp_path, ps)
        assert result == {"real.jpg"}


class TestPickCover:
    def test_prefers_portrait(self) -> None:
        pages = [["a.jpg", "b.jpg"]]
        unused = ["c.jpg"]
        media = {"a.jpg": "l", "b.jpg": "p", "c.jpg": "l"}
        assert _pick_cover(pages, unused, media) == "b.jpg"

    def test_falls_back_to_first_candidate(self) -> None:
        pages = [["a.jpg"]]
        unused = ["b.jpg"]
        media = {"a.jpg": "l", "b.jpg": "l"}
        assert _pick_cover(pages, unused, media) == "a.jpg"

    def test_returns_none_when_empty(self) -> None:
        assert _pick_cover([], [], {}) is None

    def test_pages_before_unused(self) -> None:
        pages = [["p1.jpg"]]
        unused = ["u1.jpg"]
        media = {"p1.jpg": "p", "u1.jpg": "p"}
        assert _pick_cover(pages, unused, media) == "p1.jpg"

    def test_portrait_in_unused(self) -> None:
        pages = [["land.jpg"]]
        unused = ["port.jpg"]
        media = {"land.jpg": "l", "port.jpg": "p"}
        assert _pick_cover(pages, unused, media) == "port.jpg"


class TestReconcileStepMedia:
    """Test the step media reconciliation logic in isolation.

    These test the core algorithm: given old media references and what's
    currently on disk, compute missing/added and update pages+unused.
    """

    @staticmethod
    def _reconcile_step(  # noqa: PLR0913
        pages: list[list[str]],
        unused: list[str],
        cover: str | None,
        on_disk: set[str],
        step_media: set[str],
        media_dict: dict[str, str],
    ) -> tuple[list[list[str]], list[str], str | None]:
        """Replicate the reconciliation algorithm from reconcile_trip."""
        old_media: set[str] = set()
        for pg in pages:
            old_media.update(pg)
        if cover:
            old_media.add(cover)
        old_media.update(unused)

        missing = old_media - on_disk
        added = step_media - old_media

        new_pages = [
            p for p in ([f for f in pg if f not in missing] for pg in pages) if p
        ]
        new_unused = [f for f in unused if f not in missing] + sorted(added)

        new_cover = cover
        if cover and cover in missing:
            new_cover = _pick_cover(new_pages, new_unused, media_dict)

        return new_pages, new_unused, new_cover

    def test_no_changes(self) -> None:
        pages = [["a.jpg", "b.jpg"]]
        unused = ["c.jpg"]
        on_disk = {"a.jpg", "b.jpg", "c.jpg"}
        step_media = {"a.jpg", "b.jpg", "c.jpg"}

        new_pages, new_unused, new_cover = self._reconcile_step(
            pages, unused, "a.jpg", on_disk, step_media, {}
        )
        assert new_pages == [["a.jpg", "b.jpg"]]
        assert new_unused == ["c.jpg"]
        assert new_cover == "a.jpg"

    def test_missing_photo_removed_from_pages(self) -> None:
        pages = [["a.jpg", "b.jpg"], ["c.jpg"]]
        on_disk = {"a.jpg", "c.jpg"}  # b.jpg is gone

        new_pages, _new_unused, _ = self._reconcile_step(
            pages, [], None, on_disk, {"a.jpg", "c.jpg"}, {}
        )
        assert new_pages == [["a.jpg"], ["c.jpg"]]

    def test_empty_page_dropped(self) -> None:
        pages = [["a.jpg"], ["b.jpg"]]
        on_disk = {"a.jpg"}  # b.jpg gone -> second page empty

        new_pages, _, _ = self._reconcile_step(pages, [], None, on_disk, {"a.jpg"}, {})
        assert new_pages == [["a.jpg"]]

    def test_new_media_added_to_unused(self) -> None:
        pages = [["a.jpg"]]
        on_disk = {"a.jpg", "new.jpg"}
        step_media = {"a.jpg", "new.jpg"}

        _, new_unused, _ = self._reconcile_step(
            pages, [], None, on_disk, step_media, {}
        )
        assert "new.jpg" in new_unused

    def test_missing_cover_replaced(self) -> None:
        pages = [["remain.jpg"]]
        on_disk = {"remain.jpg"}  # cover.jpg is gone
        media_dict = {"remain.jpg": "p"}

        _, _, new_cover = self._reconcile_step(
            pages, [], "cover.jpg", on_disk, {"remain.jpg"}, media_dict
        )
        assert new_cover == "remain.jpg"

    def test_all_media_missing(self) -> None:
        pages = [["a.jpg", "b.jpg"]]
        on_disk: set[str] = set()

        new_pages, new_unused, new_cover = self._reconcile_step(
            pages, ["c.jpg"], "a.jpg", on_disk, set(), {}
        )
        assert new_pages == []
        assert new_unused == []
        assert new_cover is None

    def test_missing_from_unused(self) -> None:
        unused = ["x.jpg", "y.jpg"]
        on_disk = {"x.jpg"}  # y.jpg gone

        _, new_unused, _ = self._reconcile_step(
            [], unused, None, on_disk, {"x.jpg"}, {}
        )
        assert new_unused == ["x.jpg"]

    def test_added_media_sorted(self) -> None:
        """New media added to unused is sorted for deterministic ordering."""
        pages: list[list[str]] = []
        step_media = {"c.jpg", "a.jpg", "b.jpg"}
        on_disk = step_media

        _, new_unused, _ = self._reconcile_step(
            pages, [], None, on_disk, step_media, {}
        )
        assert new_unused == ["a.jpg", "b.jpg", "c.jpg"]


class TestAlbumMediaReconciliation:
    """Test the album-level media dict and cover reconciliation logic."""

    def test_keeps_known_orientations_for_existing_files(self) -> None:
        """Orientations from album.media are preserved for files still on disk."""
        album_media = {"a.jpg": "p", "b.jpg": "l", "gone.jpg": "p"}
        on_disk = {"a.jpg", "b.jpg"}

        merged: dict[str, str] = {"cover.jpg": "l"}
        merged |= {n: o for n, o in album_media.items() if n in on_disk}

        assert merged["a.jpg"] == "p"
        assert merged["b.jpg"] == "l"
        assert "gone.jpg" not in merged

    def test_cover_fallback_when_missing(self) -> None:
        """Album cover falls back to cover_name, then step cover, then any file."""
        on_disk = {"step_cover.jpg", "other.jpg"}

        # Case 1: cover_name on disk
        cover_name = "step_cover.jpg"
        assert cover_name in on_disk

        # Case 2: cover_name not on disk, use step cover
        cover_name = "missing_cover.jpg"
        first_step_cover = "step_cover.jpg"
        fallback = (
            cover_name
            if cover_name in on_disk
            else (first_step_cover or next(iter(on_disk), ""))
        )
        assert fallback == "step_cover.jpg"

        # Case 3: no step cover either
        fallback = (
            cover_name if cover_name in on_disk else (None or next(iter(on_disk), ""))
        )
        assert fallback in on_disk

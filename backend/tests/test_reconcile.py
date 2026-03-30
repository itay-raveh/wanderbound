from pathlib import Path

from app.logic.layout.media import Media
from app.logic.reconcile import (
    _fix_album_covers,
    _pick_cover,
    _reconcile_step,
    _scan_step_media,
)
from app.models.album import Album
from app.models.polarsteps import Location, PSStep
from app.models.step import Step
from app.models.weather import Weather, WeatherData

_LOC = Location(name="Place", detail="", country_code="nl", lat=52.0, lon=4.0)
_LOC2 = Location(name="Updated", detail="center", country_code="de", lat=48.0, lon=11.0)
_WEATHER = Weather(
    day=WeatherData(temp=20.0, feels_like=18.0, icon="clear"), night=None
)


def _ps_step(step_id: int, slug: str = "step", *, location: Location = _LOC) -> PSStep:
    return PSStep.model_construct(
        id=step_id,
        name=f"Step {step_id}",
        slug=slug,
        description=f"Desc {step_id}",
        timestamp=1_700_000_000.0 + step_id * 3600,
        timezone_id="UTC",
        location=location,
    )


def _step(
    step_id: int = 1,
    *,
    pages: list[list[str]] | None = None,
    unused: list[str] | None = None,
    cover: str | None = None,
    name: str = "Old Name",
    description: str = "Old desc",
) -> Step:
    return Step(
        uid=1,
        aid="trip-1",
        id=step_id,
        name=name,
        description=description,
        cover=cover,
        pages=pages or [],
        unused=unused or [],
        timestamp=1_700_000_000.0,
        timezone_id="Europe/Amsterdam",
        location=_LOC,
        elevation=0,
        weather=_WEATHER,
    )


def _album(
    *,
    front_cover_photo: str = "front.jpg",
    back_cover_photo: str = "back.jpg",
    media: list[Media] | None = None,
) -> Album:
    return Album(
        uid=1,
        id="trip-1",
        title="Trip",
        subtitle="Sub",
        front_cover_photo=front_cover_photo,
        back_cover_photo=back_cover_photo,
        media=media or [],
        colors={},
        excluded_steps=[],
        maps_ranges=[],
        font="Assistant",
        body_font="Frank Ruhl Libre",
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

    def test_normalizes_double_jpg_extension(self, tmp_path: Path) -> None:
        ps = _ps_step(3, slug="upper")
        photos = tmp_path / ps.folder_name / "photos"
        photos.mkdir(parents=True)
        (photos / "IMG_ABC.jpg.jpg").write_bytes(b"\xff\xd8")

        result = _scan_step_media(tmp_path, ps)
        assert "IMG_ABC.jpg" in result


def _media(name: str, *, portrait: bool) -> Media:
    return Media(name=name, width=600 if portrait else 1920, height=1000 if portrait else 1080)


class TestPickCover:
    def test_prefers_portrait(self) -> None:
        pages = [["a.jpg", "b.jpg"]]
        unused = ["c.jpg"]
        media = {n: _media(n, portrait=p) for n, p in [("a.jpg", False), ("b.jpg", True), ("c.jpg", False)]}
        assert _pick_cover(pages, unused, media) == "b.jpg"

    def test_pages_before_unused(self) -> None:
        pages = [["p1.jpg"]]
        unused = ["u1.jpg"]
        media = {n: _media(n, portrait=True) for n in ("p1.jpg", "u1.jpg")}
        assert _pick_cover(pages, unused, media) == "p1.jpg"

    def test_portrait_in_unused(self) -> None:
        pages = [["land.jpg"]]
        unused = ["port.jpg"]
        media = {"land.jpg": _media("land.jpg", portrait=False), "port.jpg": _media("port.jpg", portrait=True)}
        assert _pick_cover(pages, unused, media) == "port.jpg"


class TestReconcileStep:
    def test_missing_media_removed_from_pages(self) -> None:
        step = _step(pages=[["a.jpg", "b.jpg"], ["c.jpg"]], cover="a.jpg")
        ps = _ps_step(1)
        all_on_disk = {"a.jpg", "c.jpg"}
        disk_media = {"a.jpg", "c.jpg"}

        result = _reconcile_step(step, ps, disk_media, all_on_disk, {})
        assert result.pages == [["a.jpg"], ["c.jpg"]]

    def test_empty_page_dropped(self) -> None:
        step = _step(pages=[["a.jpg"], ["b.jpg"]])
        ps = _ps_step(1)
        all_on_disk = {"a.jpg"}
        disk_media = {"a.jpg"}

        result = _reconcile_step(step, ps, disk_media, all_on_disk, {})
        assert result.pages == [["a.jpg"]]

    def test_missing_media_removed_from_unused(self) -> None:
        step = _step(unused=["x.jpg", "y.jpg"])
        ps = _ps_step(1)
        all_on_disk = {"x.jpg"}
        disk_media = {"x.jpg"}

        result = _reconcile_step(step, ps, disk_media, all_on_disk, {})
        assert result.unused == ["x.jpg"]

    def test_new_media_added_to_unused(self) -> None:
        step = _step(pages=[["a.jpg"]])
        ps = _ps_step(1)
        all_on_disk = {"a.jpg", "new.jpg"}
        disk_media = {"a.jpg", "new.jpg"}

        result = _reconcile_step(step, ps, disk_media, all_on_disk, {})
        assert "new.jpg" in result.unused

    def test_new_media_added_sorted(self) -> None:
        step = _step()
        ps = _ps_step(1)
        disk_media = {"c.jpg", "a.jpg", "b.jpg"}
        all_on_disk = disk_media

        result = _reconcile_step(step, ps, disk_media, all_on_disk, {})
        assert result.unused == ["a.jpg", "b.jpg", "c.jpg"]

    def test_missing_cover_picks_new(self) -> None:
        step = _step(pages=[["remain.jpg"]], cover="gone.jpg")
        ps = _ps_step(1)
        all_on_disk = {"remain.jpg"}
        disk_media = {"remain.jpg"}
        media_by_name = {"remain.jpg": _media("remain.jpg", portrait=True)}

        result = _reconcile_step(step, ps, disk_media, all_on_disk, media_by_name)
        assert result.cover == "remain.jpg"

    def test_cover_none_when_all_media_gone(self) -> None:
        step = _step(pages=[["a.jpg"]], unused=["b.jpg"], cover="a.jpg")
        ps = _ps_step(1)

        result = _reconcile_step(step, ps, set(), set(), {})
        assert result.cover is None
        assert result.pages == []
        assert result.unused == []

    def test_cover_not_in_missing_stays(self) -> None:
        step = _step(pages=[["a.jpg", "b.jpg"]], cover="a.jpg")
        ps = _ps_step(1)
        all_on_disk = {"a.jpg"}
        disk_media = {"a.jpg"}

        result = _reconcile_step(step, ps, disk_media, all_on_disk, {})
        assert result.cover == "a.jpg"

    def test_metadata_updated_from_ps_step(self) -> None:
        step = _step(name="Old Name", description="Old desc")
        ps = _ps_step(42, location=_LOC2)

        result = _reconcile_step(step, ps, set(), set(), {})
        assert result.name == "Step 42"
        assert result.description == "Desc 42"
        assert result.timestamp == ps.timestamp
        assert result.timezone_id == "UTC"
        assert result.location == _LOC2

    def test_new_media_not_on_disk_ignored(self) -> None:
        step = _step(pages=[["a.jpg"]])
        ps = _ps_step(1)
        disk_media = {"a.jpg", "ghost.jpg"}
        all_on_disk = {"a.jpg"}  # ghost.jpg not in flattened dir

        result = _reconcile_step(step, ps, disk_media, all_on_disk, {})
        assert "ghost.jpg" not in result.unused
        assert result.pages == [["a.jpg"]]


class TestFixAlbumCovers:
    def test_missing_cover_replaced_with_cover_name(self) -> None:
        album = _album(front_cover_photo="gone.jpg", back_cover_photo="gone2.jpg")
        all_on_disk = {"cover.jpg", "other.jpg"}
        steps = [_step(cover="step_cover.jpg")]

        _fix_album_covers(album, all_on_disk, "cover.jpg", steps)
        assert album.front_cover_photo == "cover.jpg"
        assert album.back_cover_photo == "cover.jpg"

    def test_cover_name_missing_falls_back_to_step_cover(self) -> None:
        album = _album(front_cover_photo="gone.jpg", back_cover_photo="also_gone.jpg")
        all_on_disk = {"step_cover.jpg", "other.jpg"}
        steps = [_step(cover="step_cover.jpg")]

        _fix_album_covers(album, all_on_disk, "missing_cover.jpg", steps)
        assert album.front_cover_photo == "step_cover.jpg"
        assert album.back_cover_photo == "step_cover.jpg"

    def test_only_missing_cover_replaced(self) -> None:
        album = _album(front_cover_photo="exists.jpg", back_cover_photo="gone.jpg")
        all_on_disk = {"exists.jpg", "cover.jpg"}
        steps = [_step(cover="step_cover.jpg")]

        _fix_album_covers(album, all_on_disk, "cover.jpg", steps)
        assert album.front_cover_photo == "exists.jpg"
        assert album.back_cover_photo == "cover.jpg"

    def test_skips_steps_without_cover(self) -> None:
        album = _album(front_cover_photo="gone.jpg", back_cover_photo="gone2.jpg")
        all_on_disk = {"s2_cover.jpg"}
        steps = [_step(1, cover=None), _step(2, cover="s2_cover.jpg")]

        _fix_album_covers(album, all_on_disk, "missing.jpg", steps)
        assert album.front_cover_photo == "s2_cover.jpg"
        assert album.back_cover_photo == "s2_cover.jpg"

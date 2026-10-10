import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

import app.logic.reconcile as reconcile_mod
from app.core.config import get_settings
from app.core.http_clients import HttpClients
from app.logic.layout.media import Media
from app.logic.photo_edit import validate_photo_edit
from app.logic.reconcile import (
    _fix_album_covers,
    _pick_cover,
    _reconcile_step,
    _restore_media_edits,
    _scan_step_media,
    reconcile_trip,
)
from app.logic.step_media import read_steps_with_media
from app.logic.trip_pipeline import _save_reupload
from app.logic.trip_processing import PhaseUpdate, SegmentsFound, multi_day_hike_ranges
from app.models.album import Album
from app.models.album_media import AlbumMedia, PanoramaConfig, PhotoEdit
from app.models.polarsteps import Location, PSStep
from app.models.segment import Segment
from app.models.step import StepPageLayout, StepRead, StepSlotLayout
from app.models.user import User
from tests.factories import (
    collect_async,
    create_test_jpeg,
    make_album,
    make_album_media,
    make_step_read,
    make_user,
    make_weather,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


_MOCK_HTTP = MagicMock(spec=HttpClients)
_UID = 1

_LOC = Location(name="Place", detail="", country_code="nl", lat=52.0, lon=4.0)
_LOC2 = Location(name="Updated", detail="center", country_code="de", lat=48.0, lon=11.0)
_WEATHER = make_weather(icon="clear")


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


def _page(media: list[str]) -> StepPageLayout:
    return StepPageLayout(
        id=uuid4(),
        kind="grid",
        slots=[
            StepSlotLayout(id=uuid4(), kind="photo", media_name=name) for name in media
        ],
    )


def _step(
    step_id: int = 1,
    *,
    pages: list[StepPageLayout] | None = None,
    unused: list[str] | None = None,
    cover: str | None = None,
    name: str = "Old Name",
    description: str = "Old desc",
) -> StepRead:
    return make_step_read(
        step_id=step_id,
        name=name,
        description=description,
        timezone_id="Europe/Amsterdam",
        location=_LOC,
        weather=_WEATHER,
        cover=cover,
        pages=pages,
        unused=unused,
    )


def _album(
    *,
    front_cover_photo: str = "front.jpg",
    back_cover_photo: str = "back.jpg",
) -> Album:
    return make_album(
        title="Trip",
        subtitle="Sub",
        front_cover_photo=front_cover_photo,
        back_cover_photo=back_cover_photo,
        colors={},
    )


def _user() -> User:
    return make_user(_UID, google_sub="test")


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
    return Media(
        name=name, width=600 if portrait else 1920, height=1000 if portrait else 1080
    )


class TestPickCover:
    def test_prefers_portrait(self) -> None:
        pages = [_page(["a.jpg", "b.jpg"])]
        unused = ["c.jpg"]
        media = {
            n: _media(n, portrait=p)
            for n, p in [("a.jpg", False), ("b.jpg", True), ("c.jpg", False)]
        }
        assert _pick_cover(pages, unused, media) == "b.jpg"

    def test_portrait_in_unused(self) -> None:
        pages = [_page(["land.jpg"])]
        unused = ["port.jpg"]
        media = {
            "land.jpg": _media("land.jpg", portrait=False),
            "port.jpg": _media("port.jpg", portrait=True),
        }
        assert _pick_cover(pages, unused, media) == "port.jpg"


class TestReconcileStep:
    def test_reupload_keeps_text_only_page_and_identity(self) -> None:
        text_slot = StepSlotLayout(id=uuid4(), kind="text", text="A day in Lima")
        page = StepPageLayout(id=uuid4(), kind="grid", slots=[text_slot])
        step = _step(pages=[page])

        result = _reconcile_step(step, _ps_step(1), set(), set(), {})

        assert result.pages == [page]

    def test_missing_media_removed_from_pages(self) -> None:
        step = _step(
            pages=[
                _page(["a.jpg", "b.jpg"]),
                _page(["c.jpg"]),
            ],
            cover="a.jpg",
        )
        ps = _ps_step(1)
        all_on_disk = {"a.jpg", "c.jpg"}
        disk_media = {"a.jpg", "c.jpg"}

        result = _reconcile_step(step, ps, disk_media, all_on_disk, {})
        assert [page.media for page in result.pages] == [["a.jpg"], ["c.jpg"]]

    def test_empty_page_dropped(self) -> None:
        step = _step(
            pages=[
                _page(["a.jpg"]),
                _page(["b.jpg"]),
            ]
        )
        ps = _ps_step(1)
        all_on_disk = {"a.jpg"}
        disk_media = {"a.jpg"}

        result = _reconcile_step(step, ps, disk_media, all_on_disk, {})
        assert [page.media for page in result.pages] == [["a.jpg"]]

    def test_new_media_added_to_unused(self) -> None:
        step = _step(pages=[_page(["a.jpg"])])
        ps = _ps_step(1)
        all_on_disk = {"a.jpg", "new.jpg"}
        disk_media = {"a.jpg", "new.jpg"}

        result = _reconcile_step(step, ps, disk_media, all_on_disk, {})
        assert "new.jpg" in result.unused

    def test_missing_cover_picks_new(self) -> None:
        step = _step(
            pages=[_page(["remain.jpg"])],
            cover="gone.jpg",
        )
        ps = _ps_step(1)
        all_on_disk = {"remain.jpg"}
        disk_media = {"remain.jpg"}
        media_by_name = {"remain.jpg": _media("remain.jpg", portrait=True)}

        result = _reconcile_step(step, ps, disk_media, all_on_disk, media_by_name)
        assert result.cover == "remain.jpg"

    def test_cover_none_when_all_media_gone(self) -> None:
        step = _step(
            pages=[_page(["a.jpg"])],
            unused=["b.jpg"],
            cover="a.jpg",
        )
        ps = _ps_step(1)

        result = _reconcile_step(step, ps, set(), set(), {})
        assert result.cover is None
        assert result.pages == []
        assert result.unused == []

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
        step = _step(pages=[_page(["a.jpg"])])
        ps = _ps_step(1)
        disk_media = {"a.jpg", "ghost.jpg"}
        all_on_disk = {"a.jpg"}  # ghost.jpg not in flattened dir

        result = _reconcile_step(step, ps, disk_media, all_on_disk, {})
        assert "ghost.jpg" not in result.unused
        assert [page.media for page in result.pages] == [["a.jpg"]]


class TestFixAlbumCovers:
    def test_missing_cover_replaced_with_cover_name(self) -> None:
        album = _album(front_cover_photo="gone.jpg", back_cover_photo="gone2.jpg")
        all_on_disk = {"cover.jpg", "other.jpg"}
        steps = [_step(cover="step_cover.jpg")]

        _fix_album_covers(album, all_on_disk, "cover.jpg", steps)
        assert album.chapters[0].front_cover_photo == "cover.jpg"
        assert album.chapters[0].back_cover_photo == "cover.jpg"

    def test_cover_name_missing_falls_back_to_step_cover(self) -> None:
        album = _album(front_cover_photo="gone.jpg", back_cover_photo="also_gone.jpg")
        all_on_disk = {"step_cover.jpg", "other.jpg"}
        steps = [_step(cover="step_cover.jpg")]

        _fix_album_covers(album, all_on_disk, "missing_cover.jpg", steps)
        assert album.chapters[0].front_cover_photo == "step_cover.jpg"
        assert album.chapters[0].back_cover_photo == "step_cover.jpg"

    def test_panorama_cover_is_replaced(self) -> None:
        album = _album(
            front_cover_photo="panorama.jpg",
            back_cover_photo="panorama.jpg",
        )
        eligible_covers = {"cover.jpg"}

        _fix_album_covers(album, eligible_covers, "cover.jpg", [])

        assert album.chapters[0].front_cover_photo == "cover.jpg"
        assert album.chapters[0].back_cover_photo == "cover.jpg"


_RECONCILE_AID = "test-trip_1"
_LOC_B = Location(name="B", detail="", country_code="nl", lat=52.5, lon=5.0)


def _build_trip_dir(tmp_path: Path, ps_steps: list[PSStep]) -> Path:
    trip_dir = tmp_path / _RECONCILE_AID
    trip_dir.mkdir()
    trip_json = {
        "id": 1,
        "slug": "test-trip",
        "name": "Test Trip",
        "summary": "",
        "cover_photo_path": "https://example.com/cover.jpg",
        "step_count": len(ps_steps),
        "all_steps": [s.model_dump(by_alias=True) for s in ps_steps],
    }
    (trip_dir / "trip.json").write_text(json.dumps(trip_json))
    gps_points = [
        {"lat": 52.0 + i * 0.05, "lon": 4.0 + i * 0.1, "time": 1_000_000.0 + i * 360}
        for i in range(11)
    ]
    (trip_dir / "locations.json").write_text(json.dumps({"locations": gps_points}))
    return trip_dir


def _existing_step(step_id: int, **kwargs: object) -> StepRead:
    step = _step(step_id, **kwargs)
    step.uid = _UID
    step.aid = _RECONCILE_AID
    return step


def _existing_album(
    *,
    front_cover_photo: str = "front.jpg",
    back_cover_photo: str = "back.jpg",
) -> Album:
    album = _album(
        front_cover_photo=front_cover_photo,
        back_cover_photo=back_cover_photo,
    )
    album.uid = _UID
    album.id = _RECONCILE_AID
    return album


async def _collect_reconcile(
    trip_dir: Path,
    album: Album,
    existing_steps: list[StepRead],
    *,
    existing_media_rows: list[AlbumMedia] | None = None,
) -> tuple[list, list]:
    db_out: list = []
    events = await collect_async(
        reconcile_trip(
            _MOCK_HTTP,
            _user(),
            trip_dir,
            album,
            existing_steps,
            db_out,
            existing_media_rows=existing_media_rows,
        )
    )
    return events, db_out


class TestReconcileTripRebuildsSegments:
    @pytest.mark.parametrize("removed", [True, False])
    async def test_reimport_preserves_saved_map_ranges_while_rebuilding_routes(
        self,
        tmp_path: Path,
        postgres_engine: AsyncEngine,
        monkeypatch: pytest.MonkeyPatch,
        *,
        removed: bool,
    ) -> None:
        start = datetime(2025, 5, 1, 8, tzinfo=UTC)
        points = [
            {
                "lat": 45 + (day * 8 + hour) * 0.009,
                "lon": 7 + (0.004 if hour % 2 else 0),
                "time": (start + timedelta(days=day, hours=hour)).timestamp(),
            }
            for day in range(2)
            for hour in range(9)
        ]
        ps_steps = [
            _ps_step(day + 1).model_copy(
                update={
                    "timestamp": points[day * 9]["time"],
                    "location": _LOC.model_copy(
                        update={"lat": points[day * 9]["lat"], "lon": 7}
                    ),
                }
            )
            for day in range(2)
        ]
        trip_dir = _build_trip_dir(tmp_path, ps_steps)
        (trip_dir / "locations.json").write_text(json.dumps({"locations": points}))
        album = _existing_album()
        chosen = [] if removed else [(date(2025, 5, 2), date(2025, 5, 2))]
        album.maps_ranges = chosen.copy()
        album.show_page_numbers = True
        existing = [_existing_step(ps.id) for ps in ps_steps]
        async with AsyncSession(postgres_engine, expire_on_commit=False) as session:
            session.add(_user())
            await session.flush()
            session.add(album)
            await session.flush()
            for step in existing:
                session.add_all(reconcile_mod._step_read_to_rows(step))
            await session.commit()
        monkeypatch.setattr(
            "app.logic.trip_pipeline.get_engine", lambda: postgres_engine
        )

        _, objects = await _collect_reconcile(trip_dir, album, existing)
        segments = [obj for obj in objects if isinstance(obj, Segment)]
        assert multi_day_hike_ranges(segments) == [(date(2025, 5, 1), date(2025, 5, 2))]
        assert await _save_reupload(
            _UID, objects, {_RECONCILE_AID}, {_RECONCILE_AID: album}, [trip_dir]
        )
        async with AsyncSession(postgres_engine) as session:
            saved = await session.get_one(Album, (_UID, _RECONCILE_AID))
            assert saved.maps_ranges == chosen
            assert saved.show_page_numbers is True

    async def test_segments_included_in_db_out(self, tmp_path: Path) -> None:
        ps_steps = [
            _ps_step(1, slug="start"),
            _ps_step(2, slug="end", location=_LOC_B),
        ]
        trip_dir = _build_trip_dir(tmp_path, ps_steps)

        existing_steps = [
            _existing_step(1, name="Start"),
            _existing_step(2, name="End"),
        ]
        events, db_out = await _collect_reconcile(
            trip_dir, _existing_album(), existing_steps
        )

        segments = [obj for obj in db_out if isinstance(obj, Segment)]
        segment_events = [
            event
            for event in events
            if isinstance(event, PhaseUpdate) and event.phase == "segments"
        ]
        assert segment_events == [
            PhaseUpdate(phase="segments", done=0, total=1),
            PhaseUpdate(phase="segments", done=1, total=1),
        ]
        assert any(
            isinstance(event, SegmentsFound)
            and (
                event.hikes + event.walks + event.drives + event.flights
                == len(segments)
            )
            for event in events
        )
        assert len(segments) > 0, (
            "reconcile_trip must rebuild segments from GPS data, "
            "got 0 segments in db_out (route lines would be missing)"
        )
        for seg in segments:
            assert seg.uid == _UID
            assert seg.aid == _RECONCILE_AID
            assert len(seg.points) >= 2

    async def test_preserves_existing_media_upgrade_candidate_flags(
        self, tmp_path: Path
    ) -> None:
        ps_steps = [_ps_step(1, slug="start")]
        trip_dir = _build_trip_dir(tmp_path, ps_steps)
        media_name = (
            "11111111-1111-4111-8111-111111111111_"
            "22222222-2222-4222-8222-222222222222.jpg"
        )
        source = create_test_jpeg(trip_dir / media_name, 640, 480)

        existing_steps = [
            _existing_step(
                1,
                pages=[_page([media_name])],
                cover=media_name,
            )
        ]
        existing_media = make_album_media(
            _UID,
            _RECONCILE_AID,
            name=media_name,
            kind="photo",
            width=640,
            height=480,
            byte_size=source.stat().st_size,
            upgrade_candidate=False,
        )
        existing_media.perceptual_hashes = ["0123456789abcdef"]

        _, db_out = await _collect_reconcile(
            trip_dir,
            _existing_album(front_cover_photo=media_name, back_cover_photo=media_name),
            existing_steps,
            existing_media_rows=[existing_media],
        )

        media_rows = [obj for obj in db_out if isinstance(obj, AlbumMedia)]
        row = next(obj for obj in media_rows if obj.name == media_name)
        assert row.upgrade_candidate is False
        assert row.perceptual_hashes == ["0123456789abcdef"]

    @pytest.mark.parametrize("same_byte_size", [False, True])
    async def test_changed_reuploaded_media_is_left_for_background_hashing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, same_byte_size: bool
    ) -> None:
        ps_steps = [_ps_step(1, slug="start")]
        trip_dir = _build_trip_dir(tmp_path, ps_steps)
        media_name = (
            "11111111-1111-4111-8111-111111111111_"
            "22222222-2222-4222-8222-222222222222.jpg"
        )
        source = create_test_jpeg(trip_dir / media_name, 800, 600)
        existing_media = make_album_media(
            _UID,
            _RECONCILE_AID,
            name=media_name,
            kind="photo",
            width=640,
            height=480,
            byte_size=source.stat().st_size if same_byte_size else 123,
            upgrade_candidate=False,
        )
        existing_media.perceptual_hashes = ["0123456789abcdef"]

        def fail_if_called(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("re-upload processing must not hash media")

        monkeypatch.setattr(
            "app.logic.media_upgrade.hashes.compute_serialized_media_hashes",
            fail_if_called,
        )

        _, db_out = await _collect_reconcile(
            trip_dir,
            _existing_album(front_cover_photo=media_name, back_cover_photo=media_name),
            [
                _existing_step(
                    1,
                    pages=[_page([media_name])],
                    cover=media_name,
                )
            ],
            existing_media_rows=[existing_media],
        )

        media_rows = [obj for obj in db_out if isinstance(obj, AlbumMedia)]
        row = next(obj for obj in media_rows if obj.name == media_name)
        assert row.perceptual_hashes is None
        assert row.upgrade_candidate is True
        assert (row.width, row.height) == (800, 600)

    async def test_new_reuploaded_steps_are_added_to_existing_chapter(
        self,
        tmp_path: Path,
        postgres_engine: AsyncEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ps_steps = [
            _ps_step(1, slug="start"),
            _ps_step(2, slug="new", location=_LOC_B),
        ]
        trip_dir = _build_trip_dir(tmp_path, ps_steps)
        album = _existing_album()
        album.chapters[0].step_ids = [1]
        existing = _existing_step(1, name="Start")
        monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
        user = _user()
        user.trips_folder.mkdir(parents=True)
        trip_dir = trip_dir.rename(user.trips_folder / _RECONCILE_AID)
        media_name = (
            "11111111-1111-4111-8111-111111111111_"
            "22222222-2222-4222-8222-222222222222.jpg"
        )
        create_test_jpeg(
            trip_dir / ps_steps[1].folder_name / "photos" / media_name, 640, 480
        )
        async with AsyncSession(postgres_engine, expire_on_commit=False) as session:
            session.add(_user())
            await session.flush()
            session.add(album)
            await session.flush()
            session.add_all(reconcile_mod._step_read_to_rows(existing))
            await session.commit()
        monkeypatch.setattr(
            "app.logic.trip_pipeline.get_engine", lambda: postgres_engine
        )

        def provider(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/elevation"):
                return httpx.Response(200, json={"elevation": [100]})
            if request.url.path.endswith("/archive"):
                return httpx.Response(
                    200,
                    json={
                        "daily": {
                            "time": [request.url.params["start_date"]],
                            "temperature_2m_max": [20],
                            "temperature_2m_min": [10],
                            "apparent_temperature_max": [20],
                            "apparent_temperature_min": [10],
                            "weather_code": [0],
                        }
                    },
                )
            return httpx.Response(200, json={"elements": []})

        db_out: list = []
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
            clients = HttpClients(
                open_meteo=http,
                overpass=http,
                mapbox_matching=http,
                mapbox_directions=http,
                gphotos_picker=http,
                gphotos_download=http,
                gphotos_token=http,
                gphotos_oauth=MagicMock(),
            )
            await collect_async(
                reconcile_trip(
                    clients,
                    _user(),
                    trip_dir,
                    album,
                    [_existing_step(1, name="Start")],
                    db_out,
                )
            )

        assert await _save_reupload(
            _UID,
            db_out,
            {_RECONCILE_AID},
            {_RECONCILE_AID: album},
            [trip_dir],
        )
        async with AsyncSession(postgres_engine) as persisted:
            saved_album = await persisted.get_one(Album, (_UID, _RECONCILE_AID))
            assert saved_album.chapters[0].step_ids == [1, 2]
            first = await persisted.get_one(
                reconcile_mod.Step, (_UID, _RECONCILE_AID, 1)
            )
            added = await persisted.get_one(
                reconcile_mod.Step, (_UID, _RECONCILE_AID, 2)
            )
            assert (first.name, added.name) == ("Step 1", "Step 2")
            assert added.location == _LOC_B
            saved_steps = await read_steps_with_media(persisted, _UID, _RECONCILE_AID)
            new_step = next(step for step in saved_steps if step.id == 2)
            assert [name for page in new_step.pages for name in page.media] == [
                media_name
            ]
            await persisted.get_one(AlbumMedia, (_UID, _RECONCILE_AID, media_name))


@pytest.mark.parametrize(
    "name",
    [
        "photo.jpg",
        "11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.mp4",
    ],
)
def test_reimport_does_not_transfer_photo_edits_without_a_stable_photo_identity(
    name: str,
) -> None:
    previous = make_album_media(
        name=name, kind="video" if name.endswith(".mp4") else "photo"
    )
    previous.photo_edit = PhotoEdit(angle=30, x=0.4, y=0.4, width=0.2, height=0.2)
    previous.panorama = PanoramaConfig()
    replacement = previous.model_copy(update={"photo_edit": None, "panorama": None})

    _restore_media_edits(replacement, previous)

    assert replacement.photo_edit is None
    assert replacement.panorama is None


def test_reimport_drops_invalid_panorama_projection() -> None:
    name = (
        "11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg"
    )
    previous = make_album_media(name=name, width=4000, height=1000)
    previous.panorama = PanoramaConfig()
    previous.photo_edit = PhotoEdit(angle=30, x=0.4, y=0.4, width=0.2, height=0.2)
    replacement = previous.model_copy(
        update={"width": 1000, "height": 667, "photo_edit": None, "panorama": None}
    )

    _restore_media_edits(replacement, previous)

    assert replacement.panorama is None
    assert replacement.photo_edit is not None
    validate_photo_edit(replacement.photo_edit, replacement.width, replacement.height)


@pytest.mark.parametrize("foreign_scope", ["user", "album"])
async def test_reimport_does_not_restore_another_scope_media_state(
    tmp_path: Path, *, foreign_scope: str
) -> None:
    trip_dir = _build_trip_dir(tmp_path, [_ps_step(1)])
    name = (
        "11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg"
    )
    source = create_test_jpeg(trip_dir / name, 640, 480)
    previous = make_album_media(
        _UID + 1 if foreign_scope == "user" else _UID,
        "another-trip" if foreign_scope == "album" else _RECONCILE_AID,
        name=name,
        width=640,
        height=480,
        byte_size=source.stat().st_size,
        upgrade_candidate=False,
    )
    previous.photo_edit = PhotoEdit(angle=30, x=0.4, y=0.4, width=0.2, height=0.2)
    previous.perceptual_hashes = ["0123456789abcdef"]

    _, objects = await _collect_reconcile(
        trip_dir,
        _existing_album(),
        [_existing_step(1, pages=[_page([name])])],
        existing_media_rows=[previous],
    )

    row = next(
        obj for obj in objects if isinstance(obj, AlbumMedia) and obj.name == name
    )
    assert row.photo_edit is None
    assert row.perceptual_hashes is None
    assert row.upgrade_candidate is True

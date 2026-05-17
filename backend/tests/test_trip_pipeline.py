from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.http_clients import HttpClients
from app.logic.trip_pipeline import _process_trip, _save_reupload
from app.logic.trip_processing import PhaseUpdate, SegmentsFound
from app.models.album import Album
from app.models.album_media import AlbumMedia
from app.models.polarsteps import Location
from app.models.segment import Segment, SegmentKind
from app.models.step import Step
from app.models.user import User
from app.models.weather import Weather, WeatherData
from tests.factories import collect_async, make_points

AID = "test-trip"
UID = 1
_MOCK_HTTP = MagicMock(spec=HttpClients)


def _sqlite_engine(*, foreign_keys: bool = False) -> AsyncEngine:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    if foreign_keys:
        event.listen(
            engine.sync_engine,
            "connect",
            lambda dbapi_connection, _connection_record: dbapi_connection.execute(
                "PRAGMA foreign_keys=ON"
            ),
        )
    return engine


async def _create_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


def _user() -> User:
    return User(
        id=UID,
        first_name="Test",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
        google_sub="test-sub",
    )


def _album(
    *,
    title: str = "Old Trip",
    front_cover_photo: str = "a.jpg",
    back_cover_photo: str = "b.jpg",
    font: str | None = "Assistant",
) -> Album:
    values = {
        "uid": UID,
        "id": AID,
        "title": title,
        "subtitle": "",
        "hidden_steps": [],
        "maps_ranges": [],
        "front_cover_photo": front_cover_photo,
        "back_cover_photo": back_cover_photo,
        "colors": {},
        "body_font": "Frank Ruhl Libre",
    }
    if font is not None:
        values["font"] = font
    return Album(**values)


def _step(
    *,
    step_id: int = 1,
    name: str = "Old Step",
    cover_media_name: str | None = None,
    timestamp: float = 1_000_000.0,
    temp: float = 20.0,
    feels_like: float = 18.0,
    weather_icon: str = "sun",
) -> Step:
    return Step(
        uid=UID,
        aid=AID,
        id=step_id,
        name=name,
        description="",
        cover_media_name=cover_media_name,
        timestamp=timestamp,
        timezone_id="UTC",
        location=None,
        elevation=0,
        weather=Weather(
            day=WeatherData(temp=temp, feels_like=feels_like, icon=weather_icon),
            night=None,
        ),
    )


def _reuploaded_album() -> Album:
    return _album(
        title="Reconciled Trip",
        front_cover_photo="c.jpg",
        back_cover_photo="d.jpg",
        font=None,
    )


def _reuploaded_step() -> Step:
    return _step(
        step_id=2,
        name="New Step",
        timestamp=2_000_000.0,
        temp=25.0,
        feels_like=23.0,
        weather_icon="cloud",
    )


def _segment() -> Segment:
    return Segment(
        uid=UID,
        aid=AID,
        start_time=100.0,
        end_time=500.0,
        kind=SegmentKind.driving,
        timezone_id="UTC",
        points=make_points([100.0, 300.0, 500.0]),
    )


def _cover_media() -> AlbumMedia:
    return AlbumMedia(
        uid=UID,
        aid=AID,
        name="cover.jpg",
        kind="photo",
        width=640,
        height=480,
        byte_size=10,
        upgrade_candidate=True,
    )


async def _seed_album_state(engine: AsyncEngine, *objects: object) -> None:
    async with AsyncSession(engine) as session:
        session.add(_user())
        await session.flush()
        for obj in objects:
            session.add(obj)
            await session.flush()
        await session.commit()


async def _save_reuploaded_objects(
    engine: AsyncEngine,
    tmp_path: Path,
    existing_album: Album,
    *objects: object,
) -> None:
    trip_dir = tmp_path / AID
    trip_dir.mkdir()

    with patch("app.logic.trip_pipeline.get_engine", return_value=engine):
        await _save_reupload(
            uid=UID,
            objects=list(objects),
            reconciled_aids={AID},
            existing_albums={AID: existing_album},
            trip_dirs=[trip_dir],
        )


class TestProcessTripSegmentEvents:
    async def test_emits_segment_phase_and_counts(self, tmp_path: Path) -> None:
        trip_dir = tmp_path / AID
        trip_dir.mkdir()
        location = Location(
            name="Start",
            detail="",
            country_code="nl",
            lat=52.0,
            lon=4.0,
        )
        trip = SimpleNamespace(
            title="Test Trip",
            step_count=1,
            all_steps=[SimpleNamespace(location=location)],
        )
        user = User(
            id=UID,
            first_name="Test",
            locale="en-US",
            unit_is_km=True,
            temperature_is_celsius=True,
            google_sub="test-sub",
        )
        segments = [
            Segment(
                uid=UID,
                aid=AID,
                start_time=100.0,
                end_time=200.0,
                kind=SegmentKind.driving,
                timezone_id="UTC",
                points=make_points([100.0, 200.0]),
            ),
            Segment(
                uid=UID,
                aid=AID,
                start_time=300.0,
                end_time=400.0,
                kind=SegmentKind.walking,
                timezone_id="UTC",
                points=make_points([300.0, 400.0]),
            ),
        ]
        db_out: list = []

        with (
            patch(
                "app.logic.trip_pipeline.load_trip_data",
                return_value=(trip, []),
            ),
            patch("app.logic.trip_pipeline.cover_name_from_trip", return_value=""),
            patch(
                "app.logic.trip_pipeline.run_elevations",
                new=AsyncMock(return_value=[0.0]),
            ),
            patch(
                "app.logic.trip_pipeline.run_weather",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.logic.trip_pipeline._media_pipeline",
                new=AsyncMock(return_value=({}, "")),
            ),
            patch(
                "app.logic.trip_pipeline.build_trip_objects",
                return_value=segments,
            ),
        ):
            events = await collect_async(
                _process_trip(_MOCK_HTTP, user, trip_dir, db_out)
            )

        assert PhaseUpdate(phase="segments", done=0, total=1) in events
        assert PhaseUpdate(phase="segments", done=1, total=1) in events
        assert SegmentsFound(hikes=0, walks=1, drives=1, flights=0) in events
        assert db_out == segments


class TestSaveReuploadDeletesSegments:
    async def test_reconciled_album_segments_are_deleted(self, tmp_path: Path) -> None:
        engine = _sqlite_engine()
        await _create_schema(engine)

        album = _album()
        await _seed_album_state(engine, album, _step(), _segment())

        await _save_reuploaded_objects(
            engine,
            tmp_path,
            album,
            _reuploaded_album(),
            _reuploaded_step(),
        )

        async with AsyncSession(engine) as session:
            segments = (await session.exec(select(Segment))).all()
            steps = (await session.exec(select(Step))).all()
            albums = (await session.exec(select(Album))).all()

        assert len(segments) == 0, f"Stale segments remain: {segments}"
        assert len(steps) == 1
        assert steps[0].name == "New Step"
        assert len(albums) == 1
        assert albums[0].title == "Reconciled Trip"

    async def test_reupload_deletes_steps_before_cover_media(
        self, tmp_path: Path
    ) -> None:
        engine = _sqlite_engine(foreign_keys=True)
        await _create_schema(engine)

        album = _album()
        await _seed_album_state(
            engine,
            album,
            _cover_media(),
            _step(cover_media_name="cover.jpg"),
        )

        await _save_reuploaded_objects(
            engine,
            tmp_path,
            album,
            _reuploaded_album(),
            _reuploaded_step(),
        )

        async with AsyncSession(engine) as session:
            steps = (await session.exec(select(Step))).all()
            media_rows = (await session.exec(select(AlbumMedia))).all()

        assert [s.name for s in steps] == ["New Step"]
        assert media_rows == []

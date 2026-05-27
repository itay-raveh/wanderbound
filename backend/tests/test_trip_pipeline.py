from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.http_clients import HttpClients
from app.logic.trip_pipeline import (
    _process_trip,
    _save_new,
    _save_reupload,
    run_processing,
)
from app.logic.trip_processing import ErrorData, PhaseUpdate, SegmentsFound
from app.models.album import Album
from app.models.album_media import AlbumMedia, StepPageMedia
from app.models.polarsteps import Location
from app.models.segment import Segment, SegmentKind
from app.models.step import Step
from app.models.user import User
from tests.factories import (
    collect_async,
    make_album,
    make_album_media,
    make_segment,
    make_step,
    make_user,
    make_weather,
)

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
    return make_user(UID, google_sub="test-sub")


async def test_run_processing_stale_guard_skips_db_save(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    user = _user()
    trip_dir = user.trips_folder / AID
    trip_dir.mkdir(parents=True)

    async def cancelled() -> bool:
        return False

    async def fake_process_trip(*args: object) -> AsyncIterator[PhaseUpdate]:
        yield PhaseUpdate(phase="layouts", done=1, total=1)

    with (
        patch(
            "app.logic.trip_pipeline._load_existing",
            new=AsyncMock(return_value=({}, {}, {})),
        ),
        patch("app.logic.trip_pipeline._process_trip", fake_process_trip),
        patch("app.logic.trip_pipeline._save_new", new=AsyncMock()) as save_new,
    ):
        events = await collect_async(
            run_processing(_MOCK_HTTP, user, should_continue=cancelled)
        )

    save_new.assert_not_awaited()
    assert events[-1] == ErrorData()


async def test_save_new_guard_skips_commit_inside_save_transaction(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    engine = _sqlite_engine()
    await _create_schema(engine)
    album = _album()

    async def stale(_session: AsyncSession) -> bool:
        return False

    with patch("app.logic.trip_pipeline.get_engine", return_value=engine):
        saved = await _save_new(UID, [album], save_guard=stale)

    async with AsyncSession(engine) as session:
        rows = (await session.exec(select(Album))).all()

    assert saved is False
    assert rows == []


def _album(
    *,
    title: str = "Old Trip",
    front_cover_photo: str = "a.jpg",
    back_cover_photo: str = "b.jpg",
    font: str | None = "Assistant",
) -> Album:
    return make_album(
        UID,
        AID,
        title=title,
        subtitle="",
        front_cover_photo=front_cover_photo,
        back_cover_photo=back_cover_photo,
        colors={},
        font=font,
    )


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
    return make_step(
        UID,
        AID,
        step_id=step_id,
        name=name,
        description="",
        timestamp=timestamp,
        timezone_id="UTC",
        location=None,
        elevation=0,
        weather=make_weather(temp=temp, feels_like=feels_like, icon=weather_icon),
        cover_media_name=cover_media_name,
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
    return make_segment(
        UID,
        AID,
        start_time=100.0,
        end_time=500.0,
        kind=SegmentKind.driving,
    )


def _cover_media() -> AlbumMedia:
    return make_album_media(
        UID,
        AID,
        name="cover.jpg",
        kind="photo",
        width=640,
        height=480,
        byte_size=10,
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
        user = _user()
        segments = [
            make_segment(
                UID,
                AID,
                start_time=100.0,
                end_time=200.0,
                kind=SegmentKind.driving,
            ),
            make_segment(
                UID,
                AID,
                start_time=300.0,
                end_time=400.0,
                kind=SegmentKind.walking,
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


class TestSaveNew:
    async def test_flushes_parent_rows_before_step_media(self) -> None:
        engine = _sqlite_engine(foreign_keys=True)
        await _create_schema(engine)

        await _seed_album_state(engine)

        album = _album()
        media = make_album_media(
            UID,
            AID,
            name="page.jpg",
            kind="photo",
            width=640,
            height=480,
            byte_size=10,
        )
        step = _step(step_id=191160695)
        page_media = StepPageMedia(
            uid=UID,
            aid=AID,
            step_id=step.id,
            page_index=0,
            position_index=0,
            media_name=media.name,
        )
        expected = (UID, AID, step.id, 0, 0, media.name)

        with patch("app.logic.trip_pipeline.get_engine", return_value=engine):
            await _save_new(UID, [album, media, step, page_media])

        async with AsyncSession(engine) as session:
            rows = (await session.exec(select(StepPageMedia))).all()

        assert [
            (
                row.uid,
                row.aid,
                row.step_id,
                row.page_index,
                row.position_index,
                row.media_name,
            )
            for row in rows
        ] == [expected]


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

    async def test_reupload_flushes_parent_rows_before_step_media(
        self, tmp_path: Path
    ) -> None:
        engine = _sqlite_engine(foreign_keys=True)
        await _create_schema(engine)

        album = _album()
        await _seed_album_state(engine, album, _step())
        media = make_album_media(
            UID,
            AID,
            name="page.jpg",
            kind="photo",
            width=640,
            height=480,
            byte_size=10,
        )
        step = _reuploaded_step()
        page_media = StepPageMedia(
            uid=UID,
            aid=AID,
            step_id=step.id,
            page_index=0,
            position_index=0,
            media_name=media.name,
        )

        await _save_reuploaded_objects(
            engine,
            tmp_path,
            album,
            _reuploaded_album(),
            media,
            step,
            page_media,
        )

        async with AsyncSession(engine) as session:
            rows = (await session.exec(select(StepPageMedia))).all()

        assert [
            (
                row.uid,
                row.aid,
                row.step_id,
                row.page_index,
                row.position_index,
                row.media_name,
            )
            for row in rows
        ] == [(UID, AID, 2, 0, 0, "page.jpg")]

import json
from collections.abc import AsyncIterator
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4
from zipfile import ZipFile

import pytest
from PIL import Image
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.http_clients import HttpClients
from app.logic.media_upgrade.phash_matching import MatchResult
from app.logic.media_upgrade.upgrade import _persist_upgrade_in_session
from app.logic.photo_edit import render_photo_edit, validate_photo_edit
from app.logic.reconcile import _step_read_to_rows, reconcile_trip
from app.logic.trip_pipeline import (
    _load_existing,
    _save_new,
    _save_reupload,
    run_processing,
)
from app.logic.trip_processing import ErrorData, PhaseUpdate
from app.logic.upload import extract_and_scan
from app.logic.uploads.finalize import replace_folder_once
from app.models.album import Album
from app.models.album_media import (
    AlbumMedia,
    PhotoEdit,
    StepPage,
    StepPageSlot,
    StepUnusedMedia,
)
from app.models.segment import Segment, SegmentKind
from app.models.step import Step, StepPageLayout, StepSlotLayout
from app.models.user import User
from tests.factories import (
    DEFAULT_MEDIA_NAME,
    collect_async,
    create_test_jpeg,
    make_album,
    make_album_media,
    make_ps_step,
    make_segment,
    make_step,
    make_step_read,
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

    engine = _sqlite_engine()
    await _create_schema(engine)

    async def fake_process_trip(
        _http: HttpClients,
        _user: User,
        _trip_dir: Path,
        db_out: list,
    ) -> AsyncIterator[PhaseUpdate]:
        db_out.append(_album(title="Stale run must not persist"))
        yield PhaseUpdate(phase="layouts", done=1, total=1)

    try:
        with (
            patch("app.logic.trip_pipeline.get_engine", return_value=engine),
            patch("app.logic.trip_pipeline._process_trip", fake_process_trip),
        ):
            events = await collect_async(
                run_processing(_MOCK_HTTP, user, should_continue=cancelled)
            )
        async with AsyncSession(engine) as session:
            assert (await session.exec(select(Album))).all() == []
        assert events[-1] == ErrorData()
    finally:
        await engine.dispose()


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


def _page() -> StepPage:
    return StepPage(
        uid=UID,
        aid=AID,
        step_id=1,
        id="page-1",
        position_index=0,
    )


def _page_media() -> StepPageSlot:
    return StepPageSlot(
        uid=UID,
        aid=AID,
        step_id=1,
        id="slot-1",
        page_id="page-1",
        position_index=0,
        kind="photo",
        media_name="cover.jpg",
        continuation_priority=0,
    )


def _unused_media() -> StepUnusedMedia:
    return StepUnusedMedia(
        uid=UID,
        aid=AID,
        step_id=1,
        position_index=0,
        media_name="cover.jpg",
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


class TestSaveNewDependencyOrder:
    async def test_saves_step_media_after_parent_step_and_album_media(
        self,
    ) -> None:
        engine = _sqlite_engine(foreign_keys=True)
        await _create_schema(engine)
        await _seed_album_state(engine)

        saved = False
        with patch("app.logic.trip_pipeline.get_engine", return_value=engine):
            saved = await _save_new(
                UID,
                [
                    _album(),
                    _cover_media(),
                    _step(),
                    _page(),
                    _page_media(),
                    _unused_media(),
                ],
            )

        async with AsyncSession(engine) as session:
            page_media = (await session.exec(select(StepPageSlot))).all()
            unused_media = (await session.exec(select(StepUnusedMedia))).all()

        assert saved is True
        assert page_media == [_page_media()]
        assert unused_media == [_unused_media()]


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
        assert albums[0].chapters[0].title == "Reconciled Trip"

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
        page = StepPage(
            uid=UID, aid=AID, step_id=step.id, id="page-2", position_index=0
        )
        page_media = StepPageSlot(
            uid=UID,
            aid=AID,
            step_id=step.id,
            id="slot-2",
            page_id="page-2",
            position_index=0,
            kind="photo",
            media_name=media.name,
            continuation_priority=0,
        )

        await _save_reuploaded_objects(
            engine,
            tmp_path,
            album,
            _reuploaded_album(),
            media,
            step,
            page,
            page_media,
        )

        async with AsyncSession(engine) as session:
            rows = (await session.exec(select(StepPageSlot))).all()

        assert [
            (
                row.uid,
                row.aid,
                row.step_id,
                row.page_id,
                row.position_index,
                row.media_name,
            )
            for row in rows
        ] == [(UID, AID, 2, "page-2", 0, "page.jpg")]


@pytest.mark.parametrize("original_source", [False, True])
async def test_upgrade_then_zip_reimport_preserves_composition(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, original_source: bool
) -> None:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    engine = _sqlite_engine(foreign_keys=True)
    await _create_schema(engine)
    monkeypatch.setattr("app.logic.trip_pipeline.get_engine", lambda: engine)
    user = _user()
    user.album_ids = [AID]
    album_dir = user.trips_folder / AID
    source = create_test_jpeg(album_dir / DEFAULT_MEDIA_NAME, 1000, 667)
    unused_source = create_test_jpeg(
        album_dir
        / (
            "33333333-3333-4333-8333-333333333333_"
            "44444444-4444-4444-8444-444444444444.jpg"
        ),
        600,
        900,
    )
    unused_bytes = unused_source.read_bytes()
    original = source.read_bytes()
    media = make_album_media(
        UID,
        AID,
        name=source.name,
        width=1000,
        height=667,
        byte_size=source.stat().st_size,
    )
    media.photo_edit = PhotoEdit(
        angle=30,
        x=0.24526177829903595,
        y=0.3092192924887657,
        width=0.5139281951109125,
        height=0.38156141502246865,
    )
    text_page = StepPageLayout(
        id=uuid4(),
        kind="grid",
        slots=[
            StepSlotLayout(
                id=uuid4(),
                kind="text",
                text="שלום Amsterdam\nQA",
                continuation_priority=0,
            )
        ],
    )
    photo_page = StepPageLayout(
        id=uuid4(),
        kind="grid",
        slots=[
            StepSlotLayout(
                id=uuid4(),
                kind="photo",
                media_name=source.name,
                continuation_priority=1,
            )
        ],
    )
    # Deliberately retain the user's text-before-photo page order.
    step = make_step_read(
        UID,
        AID,
        pages=[text_page, photo_page],
        cover=source.name,
        unused=[unused_source.name],
    )
    album = _album(front_cover_photo=source.name, back_cover_photo=source.name)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(user)
        await session.flush()
        session.add(album)
        await session.flush()
        session.add(media)
        session.add(
            make_album_media(
                UID,
                AID,
                name=unused_source.name,
                width=600,
                height=900,
                byte_size=len(unused_bytes),
            )
        )
        await session.flush()
        for row in _step_read_to_rows(step):
            session.add(row)
            await session.flush()
        await session.commit()
        create_test_jpeg(source, 3000, 2000)
        await _persist_upgrade_in_session(
            session,
            uid=UID,
            aid=AID,
            album_dir=album_dir,
            matches=[
                MatchResult(
                    local_name=source.name, google_id="local-fixture", distance=0
                )
            ],
            succeeded={source.name},
        )
        before = media.photo_edit
        assert before is not None
        # Both variants start with an actual persisted quality upgrade.
        archive = BytesIO()
        trip = {
            "id": 1,
            "slug": "test-trip",
            "name": "Trip",
            "summary": "",
            "cover_photo_path": "https://example.com/" + source.name,
            "step_count": 1,
            "all_steps": [make_ps_step(1, slug="step").model_dump(by_alias=True)],
        }
        with ZipFile(archive, "w") as zipped:
            zipped.writestr(
                "user/user.json",
                json.dumps(
                    {
                        "id": UID,
                        "first_name": "QA",
                        "locale": "en_US",
                        "unit_is_km": True,
                        "temperature_is_celsius": True,
                    }
                ),
            )
            zipped.writestr(f"trip/{AID}/trip.json", json.dumps(trip))
            zipped.writestr(f"trip/{AID}/locations.json", '{"locations":[]}')
            zipped.writestr(
                f"trip/{AID}/step_1/photos/{source.name}",
                original if original_source else source.read_bytes(),
            )
            zipped.writestr(
                f"trip/{AID}/step_1/photos/{unused_source.name}", unused_bytes
            )
        archive.seek(0)
        extracted, _, _ = extract_and_scan(archive)
        replace_folder_once(extracted / "trip" / AID, album_dir, marker="qa-reimport")
        albums, medias, steps = await _load_existing(user)
        objects = []
        await collect_async(
            reconcile_trip(
                _MOCK_HTTP,
                user,
                album_dir,
                albums[AID],
                steps[AID],
                objects,
                existing_media_rows=medias[AID],
            )
        )
        await _save_reupload(
            uid=UID,
            objects=objects,
            reconciled_aids={AID},
            existing_albums=albums,
            trip_dirs=[album_dir],
        )
        session.expire_all()
        await session.refresh(user)
        saved = await session.get_one(AlbumMedia, (UID, AID, source.name))
        assert saved.photo_edit is not None
        assert saved.photo_edit.angle == before.angle
        assert (saved.width, saved.height) == (
            (1000, 667) if original_source else (3000, 2000)
        )
        validate_photo_edit(saved.photo_edit, saved.width, saved.height)
        if not original_source:
            assert saved.photo_edit == before
        rendered = await render_photo_edit(
            album_dir, source, saved.photo_edit, source.name
        )
        with Image.open(rendered) as image:
            assert image.width > 0
            assert image.height > 0
        _, _, saved_steps = await _load_existing(user)
        assert saved_steps[AID][0].pages == [text_page, photo_page]
        assert saved_steps[AID][0].unused == [unused_source.name]
    await engine.dispose()

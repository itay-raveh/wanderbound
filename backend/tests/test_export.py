from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from app.core.config import get_settings

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession
from app.logic.export import (
    _EXPORT_NAME,
    EXPORT_FILENAME,
    ExportDone,
    ExportError,
    ExportEvent,
    ExportProgress,
    _tokens as export_tokens,
    export_user_data,
    pop_export_token,
)
from app.logic.layout.media import Media
from app.models.album import Album
from app.models.polarsteps import Location, Point
from app.models.segment import Segment
from app.models.step import Step
from app.models.user import User
from app.models.weather import Weather, WeatherData
from tests.factories import collect_async


def _make_user(uid: int, tmp_path: Path, *, album_ids: list[str] | None = None) -> User:
    user = User(
        id=uid,
        google_sub=f"google-{uid}",
        first_name="Test",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
        album_ids=album_ids or ["trip-1"],
    )
    user.folder.mkdir(parents=True, exist_ok=True)
    return user


_LOCATION = Location(name="Test", detail="Place", country_code="NL", lat=52.0, lon=4.0)
_WEATHER = Weather(day=WeatherData(temp=20.0, feels_like=18.0, icon="clear_day"))


async def _insert_album(session: AsyncSession, uid: int, aid: str) -> Album:
    album = Album(
        uid=uid,
        id=aid,
        title="Test Album",
        subtitle="Test Subtitle",
        hidden_steps=[],
        front_cover_photo="cover.jpg",
        back_cover_photo="back.jpg",
        colors={"NL": "#FF6B35"},
        media=[Media(name="photo1.jpg", width=1920, height=1080)],
        font="Assistant",
        body_font="Frank Ruhl Libre",
    )
    session.add(album)
    await session.flush()
    return album


async def _insert_step(session: AsyncSession, uid: int, aid: str, sid: int) -> Step:
    step = Step(
        uid=uid,
        aid=aid,
        id=sid,
        name="Step One",
        description="A test step",
        cover="photo1.jpg",
        pages=[["photo1.jpg"]],
        unused=[],
        timestamp=1700000000.0,
        timezone_id="Europe/Amsterdam",
        location=_LOCATION,
        elevation=10,
        weather=_WEATHER,
    )
    session.add(step)
    await session.flush()
    return step


async def _insert_segment(session: AsyncSession, uid: int, aid: str) -> Segment:
    seg = Segment(
        uid=uid,
        aid=aid,
        start_time=1700000000.0,
        end_time=1700003600.0,
        kind="walking",
        timezone_id="UTC",
        points=[
            Point(lat=52.0, lon=4.0, time=1700000000.0),
            Point(lat=52.1, lon=4.1, time=1700003600.0),
        ],
    )
    session.add(seg)
    await session.flush()
    return seg


class TestTokenManagement:
    @pytest.fixture(autouse=True)
    def _clean_tokens(self) -> None:
        export_tokens.cleanup()

    async def test_store_and_pop(self, tmp_path: Path) -> None:
        path = tmp_path / "test.zip"
        path.write_bytes(b"fake zip")

        token = export_tokens.store(path)
        assert isinstance(token, str)
        assert len(token) > 10

        result = pop_export_token(token)
        assert result == path

        # Second pop returns None
        assert pop_export_token(token) is None

    async def test_pop_unknown_token(self) -> None:
        assert pop_export_token("nonexistent") is None


class TestExportUserData:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        export_tokens.cleanup()
        monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
        (tmp_path / "users").mkdir(exist_ok=True)

    async def test_yields_progress_and_done(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = 7001
        user = _make_user(uid, tmp_path)

        # Set up media on disk
        trip_dir = user.trips_folder / "trip-1"
        trip_dir.mkdir(parents=True)
        (trip_dir / "photo1.jpg").write_bytes(b"\xff\xd8fake jpeg")

        # Insert DB records
        await _insert_album(session, uid, "trip-1")
        await _insert_step(session, uid, "trip-1", 1)
        await _insert_segment(session, uid, "trip-1")
        await session.flush()

        events: list[ExportEvent] = await collect_async(export_user_data(user, session))

        progress_events = [e for e in events if isinstance(e, ExportProgress)]
        done_events = [e for e in events if isinstance(e, ExportDone)]

        assert len(progress_events) >= 2  # initial 0 + at least one update
        assert progress_events[0].files_done == 0
        assert (
            progress_events[0].files_total == 5
        )  # 1 account + 3 album JSONs + 1 photo
        assert len(done_events) == 1

        # Verify the ZIP contents
        path = pop_export_token(done_events[0].token)
        assert path is not None

        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            assert f"{_EXPORT_NAME}/account.json" in names
            assert f"{_EXPORT_NAME}/albums/trip-1/album.json" in names
            assert f"{_EXPORT_NAME}/albums/trip-1/steps.json" in names
            assert f"{_EXPORT_NAME}/albums/trip-1/segments.json" in names
            assert f"{_EXPORT_NAME}/albums/trip-1/media/photo1.jpg" in names

        path.unlink(missing_ok=True)

    async def test_excludes_provider_subs(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = 7002
        user = _make_user(uid, tmp_path, album_ids=[])

        events = await collect_async(export_user_data(user, session))
        done_events = [e for e in events if isinstance(e, ExportDone)]
        assert len(done_events) == 1

        path = pop_export_token(done_events[0].token)
        assert path is not None

        with zipfile.ZipFile(path) as zf:
            account = json.loads(zf.read(f"{_EXPORT_NAME}/account.json"))

        assert "google_sub" not in account
        assert "microsoft_sub" not in account
        assert account["first_name"] == "Test"
        path.unlink(missing_ok=True)

    async def test_empty_user_still_produces_zip(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = 7003
        user = _make_user(uid, tmp_path, album_ids=[])

        events = await collect_async(export_user_data(user, session))
        done_events = [e for e in events if isinstance(e, ExportDone)]
        assert len(done_events) == 1

        path = pop_export_token(done_events[0].token)
        assert path is not None

        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            assert f"{_EXPORT_NAME}/account.json" in names
            assert len(names) == 1

        path.unlink(missing_ok=True)

    async def test_error_on_zip_failure(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = 7004
        user = _make_user(uid, tmp_path, album_ids=[])

        with patch("app.logic.export._build_zip", side_effect=OSError("disk full")):
            events = await collect_async(export_user_data(user, session))

        error_events = [e for e in events if isinstance(e, ExportError)]
        assert len(error_events) == 1


class TestDownloadExport:
    async def test_valid_token_returns_zip(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        zip_path = tmp_path / "test-export.zip"
        zip_path.write_bytes(b"PK\x03\x04 fake zip")

        with patch(
            "app.api.v1.routes.users.pop_export_token",
            return_value=zip_path,
        ):
            resp = await client.get("/api/v1/users/export/download/valid-token")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert EXPORT_FILENAME in resp.headers.get("content-disposition", "")
        assert resp.content == b"PK\x03\x04 fake zip"

    async def test_invalid_token_returns_404(self, client: AsyncClient) -> None:
        with patch(
            "app.api.v1.routes.users.pop_export_token",
            return_value=None,
        ):
            resp = await client.get("/api/v1/users/export/download/bad-token")

        assert resp.status_code == 404

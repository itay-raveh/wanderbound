from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.tokens import ArtifactTokenStore
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
from app.models.processing import ArtifactToken
from app.models.user import User
from tests.factories import (
    AID,
    collect_async,
    insert_album,
    insert_segment,
    insert_step,
    make_user,
)
from tests.helpers.users import UserRoutes


def _export_path(*parts: str) -> str:
    return str(Path(_EXPORT_NAME, *parts))


def _done_event(events: list[ExportEvent]) -> ExportDone:
    done_events = [e for e in events if isinstance(e, ExportDone)]
    assert len(done_events) == 1
    return done_events[0]


async def _export_events_and_path(
    user: User, session: AsyncSession
) -> tuple[list[ExportEvent], Path]:
    events: list[ExportEvent] = await collect_async(export_user_data(user, session))
    path = await pop_export_token(session, _done_event(events).token)
    assert path is not None
    return events, path


def _zip_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


def _read_zip_json(path: Path, member: str) -> Any:
    with zipfile.ZipFile(path) as zf:
        return json.loads(zf.read(member))


def _export_download_token(path: Path | None) -> patch:
    return patch(
        "app.api.v1.routes.users.pop_export_token",
        new=AsyncMock(return_value=path),
    )


class TestTokenManagement:
    @pytest.fixture(autouse=True)
    def _clean_tokens(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
        export_tokens.cleanup()

    async def test_store_and_pop(self, tmp_path: Path, session: AsyncSession) -> None:
        path = tmp_path / "test.zip"
        path.write_bytes(b"fake zip")

        token = await export_tokens.store(session, path)
        assert isinstance(token, str)
        assert len(token) > 10
        assert await session.get(ArtifactToken, token) is not None
        assert not (tmp_path / "tokens" / _EXPORT_NAME / "manifests").exists()

        result = await pop_export_token(session, token)
        assert result == path

        assert await pop_export_token(session, token) is None

    async def test_concurrent_pop_only_returns_token_once(
        self, tmp_path: Path, session: AsyncSession, engine: Any
    ) -> None:
        path = tmp_path / "test.zip"
        path.write_bytes(b"fake zip")
        token = await export_tokens.store(session, path)

        ready = 0
        release = asyncio.Event()

        class CoordinatedSession:
            def __init__(self, inner: AsyncSession) -> None:
                self._inner = inner

            async def get(self, *args: object, **kwargs: object) -> object:
                nonlocal ready
                row = await self._inner.get(*args, **kwargs)
                ready += 1
                if ready == 2:
                    release.set()
                await release.wait()
                return row

            def __getattr__(self, name: str) -> object:
                return getattr(self._inner, name)

        async def pop_once() -> Path | None:
            async with AsyncSession(engine, expire_on_commit=False) as inner:
                return await pop_export_token(
                    CoordinatedSession(inner),  # type: ignore[arg-type]
                    token,
                )

        results = await asyncio.wait_for(
            asyncio.gather(pop_once(), pop_once()), timeout=1
        )

        assert sorted(results, key=lambda value: value is None) == [path, None]

    async def test_lifespan_periodically_evicts_undownloaded_tokens(
        self, tmp_path: Path
    ) -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tokens.db'}")
        removed: list[Path] = []
        store = ArtifactTokenStore(
            dir_name="test-artifacts",
            ttl=0,
            label="test artifact",
            cleanup_interval=0.01,
            on_evict=lambda data: removed.append(Path(data["path"])),
        )
        try:
            async with engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            async with store.lifespan(engine=engine):
                path = store.make_dest(".zip")
                path.write_bytes(b"fake zip")
                async with AsyncSession(engine, expire_on_commit=False) as session:
                    token = await store.store(session, {"path": str(path)})

                async def wait_until_deleted() -> None:
                    async with AsyncSession(engine) as poll:
                        while await poll.get(ArtifactToken, token) is not None:
                            await poll.rollback()
                            await asyncio.sleep(0.01)

                await asyncio.wait_for(wait_until_deleted(), timeout=1)

            assert removed == [path]
        finally:
            await engine.dispose()


class TestExportUserData:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        export_tokens.cleanup()
        monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
        (tmp_path / "users").mkdir(exist_ok=True)

    async def test_yields_progress_and_done(self, session: AsyncSession) -> None:
        uid = 7001
        user = make_user(uid)

        trip_dir = user.trips_folder / AID
        trip_dir.mkdir(parents=True)
        (trip_dir / "photo1.jpg").write_bytes(b"\xff\xd8fake jpeg")

        await insert_album(session, uid)
        await insert_step(session, uid)
        await insert_segment(session, uid)
        await session.flush()

        events, path = await _export_events_and_path(user, session)

        progress_events = [e for e in events if isinstance(e, ExportProgress)]

        assert len(progress_events) >= 2
        assert progress_events[0].files_done == 0
        assert progress_events[0].files_total == 5
        assert {
            _export_path("account.json"),
            _export_path("albums", AID, "album.json"),
            _export_path("albums", AID, "steps.json"),
            _export_path("albums", AID, "segments.json"),
            _export_path("albums", AID, "media", "photo1.jpg"),
        }.issubset(_zip_names(path))

        path.unlink(missing_ok=True)

    async def test_empty_user_still_produces_zip(self, session: AsyncSession) -> None:
        uid = 7003
        user = make_user(uid, album_ids=[])

        _, path = await _export_events_and_path(user, session)
        names = _zip_names(path)
        assert _export_path("account.json") in names
        assert len(names) == 1

        path.unlink(missing_ok=True)

    async def test_steps_json_includes_normalized_media_layout(
        self, session: AsyncSession
    ) -> None:
        uid = 7005
        user = make_user(uid)
        trip_dir = user.trips_folder / AID
        trip_dir.mkdir(parents=True)

        await insert_album(session, uid)
        await insert_step(
            session,
            uid,
            cover_media_name="photo1.jpg",
            page_media_name="page.jpg",
            unused_media_name="unused.jpg",
        )
        await session.flush()

        _, path = await _export_events_and_path(user, session)
        steps = _read_zip_json(path, _export_path("albums", AID, "steps.json"))

        assert steps[0]["cover"] == "photo1.jpg"
        assert steps[0]["pages"] == [["page.jpg"]]
        assert steps[0]["unused"] == ["unused.jpg"]
        assert "cover_media_name" not in steps[0]
        path.unlink(missing_ok=True)

    async def test_error_on_zip_failure(self, session: AsyncSession) -> None:
        uid = 7004
        user = make_user(uid, album_ids=[])

        with patch("app.logic.export._build_zip", side_effect=OSError("disk full")):
            events = await collect_async(export_user_data(user, session))

        error_events = [e for e in events if isinstance(e, ExportError)]
        assert len(error_events) == 1


class TestDownloadExport:
    async def test_valid_token_returns_zip(
        self, user_routes: UserRoutes, tmp_path: Path
    ) -> None:
        zip_path = tmp_path / "test-export.zip"
        zip_path.write_bytes(b"PK\x03\x04 fake zip")

        with _export_download_token(zip_path):
            resp = await user_routes.download_export("valid-token")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert EXPORT_FILENAME in resp.headers.get("content-disposition", "")
        assert resp.content == b"PK\x03\x04 fake zip"

    async def test_invalid_token_returns_404(self, user_routes: UserRoutes) -> None:
        with _export_download_token(None):
            resp = await user_routes.download_export("bad-token")

        assert resp.status_code == 404

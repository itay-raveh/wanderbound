from __future__ import annotations

import asyncio
import inspect
import io
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import anyio
import pytest
from httpx_oauth.oauth2 import OAuth2Token
from PIL import Image
from pydantic import TypeAdapter
from sqlmodel import col, select

from app.api.v1.deps import _get_http_clients
from app.api.v1.routes.media_imports import _download_google_items, import_google_media
from app.core.config import get_settings
from app.logic.layout.media import Media, MediaName
from app.logic.media_import import (
    ImportRequest,
    SavedInput,
    _import_one,
    import_saved_media,
    persist_imported_media,
    process_saved_media,
)
from app.main import app
from app.models.album import Album
from app.models.album_media import AlbumMedia
from app.models.google_photos import GoogleMediaFile, PickedMediaItem
from app.models.step import Step
from app.services.google_photos import DownloadTooLargeError

from .conftest import _mock_http_clients
from .factories import (
    AID,
    connect_google_photos,
    insert_album,
    insert_album_media,
    insert_step,
    sign_in_and_upload,
)

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlmodel.ext.asyncio.session import AsyncSession

_media_name_adapter = TypeAdapter(MediaName)


def _jpeg_bytes(width: int = 640, height: int = 480) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="red").save(buf, "JPEG")
    return buf.getvalue()


async def _signed_in_album(
    client: AsyncClient,
    session: AsyncSession,
    users_dir: Path,
) -> int:
    user_data = await sign_in_and_upload(client, users_dir, provider="google")
    uid = user_data["id"]
    album = await insert_album(session, uid)
    album.front_cover_photo = "photo1.jpg"
    album.back_cover_photo = "photo1.jpg"
    await insert_album_media(session, uid, name="photo1.jpg")
    await insert_step(session, uid)
    album_dir = users_dir / str(uid) / "trip" / AID
    album_dir.mkdir(parents=True, exist_ok=True)
    await session.flush()
    return uid


async def _no_saved_inputs(**_kwargs: object) -> AsyncIterator[SavedInput]:
    for item in ():
        yield item


class TestDeviceMediaImport:
    async def test_step_import_prepends_to_unused(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        uid = await _signed_in_album(client, session, get_settings().USERS_FOLDER)

        resp = await client.post(
            f"/api/v1/albums/{AID}/media-imports/device",
            data={"context": "step", "step_id": "1"},
            files=[
                ("files", ("holiday.jpg", _jpeg_bytes(640, 480), "image/jpeg")),
                ("files", ("ignored-name.jpg", _jpeg_bytes(800, 600), "image/jpeg")),
            ],
        )

        assert resp.status_code == 200
        imported = resp.json()["names"]
        assert len(imported) == 2
        for name in imported:
            _media_name_adapter.validate_python(name)

        step = await session.get_one(Step, (uid, AID, 1))
        assert step.unused[:2] == imported
        assert step.unused[2:] == ["photo2.jpg"]

        media_rows = (
            await session.exec(
                select(AlbumMedia)
                .where(AlbumMedia.uid == uid, AlbumMedia.aid == AID)
                .order_by(col(AlbumMedia.created_at), col(AlbumMedia.name))
            )
        ).all()
        assert [row.name for row in media_rows][-2:] == imported

    async def test_cover_import_does_not_select_cover(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        uid = await _signed_in_album(client, session, get_settings().USERS_FOLDER)

        resp = await client.post(
            f"/api/v1/albums/{AID}/media-imports/device",
            data={"context": "cover"},
            files={"files": ("cover.jpg", _jpeg_bytes(900, 600), "image/jpeg")},
        )

        assert resp.status_code == 200
        imported = resp.json()["names"]
        assert len(imported) == 1

        album = await session.get_one(Album, (uid, AID))
        assert album.front_cover_photo == "photo1.jpg"
        assert album.back_cover_photo == "photo1.jpg"
        row = await session.get_one(AlbumMedia, (uid, AID, imported[0]))
        assert row.name == imported[0]

        step = await session.get_one(Step, (uid, AID, 1))
        assert step.unused == ["photo2.jpg"]

    async def test_rejects_more_than_fifty_files(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await _signed_in_album(client, session, get_settings().USERS_FOLDER)

        resp = await client.post(
            f"/api/v1/albums/{AID}/media-imports/device",
            data={"context": "cover"},
            files=[
                ("files", (f"{i}.jpg", _jpeg_bytes(), "image/jpeg")) for i in range(51)
            ],
        )

        assert resp.status_code == 413

    async def test_rejects_missing_step_before_saving_uploads(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await _signed_in_album(client, session, get_settings().USERS_FOLDER)

        with patch(
            "app.logic.media_import.save_uploads",
            AsyncMock(),
        ) as save_uploads:
            resp = await client.post(
                f"/api/v1/albums/{AID}/media-imports/device",
                data={"context": "step", "step_id": "999"},
                files={"files": ("holiday.jpg", _jpeg_bytes(), "image/jpeg")},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Step not found"
        save_uploads.assert_not_awaited()


class TestGoogleMediaImport:
    @pytest.fixture(autouse=True)
    def _pin_route_engine(self, engine: AsyncEngine) -> Iterator[None]:
        with patch("app.api.v1.routes.media_imports.get_engine", return_value=engine):
            yield

    def test_google_import_stream_does_not_request_route_session(self) -> None:
        assert "session" not in inspect.signature(import_google_media).parameters

    async def test_import_session_uses_fifty_item_picker_limit(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        users_dir = get_settings().USERS_FOLDER
        uid = await _signed_in_album(client, session, users_dir)
        await connect_google_photos(session, uid)

        http = _mock_http_clients()
        app.dependency_overrides[_get_http_clients] = lambda: http
        http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
            {"access_token": "fresh-token", "expires_in": 3600}
        )
        mock_picker = AsyncMock()
        mock_picker.return_value.id = "session-abc"
        mock_picker.return_value.picker_uri = "https://photos.google.com/picker/abc"

        with patch(
            "app.api.v1.routes.media_imports.create_picker_session",
            mock_picker,
        ):
            resp = await client.post(
                f"/api/v1/albums/{AID}/media-imports/google/session"
            )

        assert resp.status_code == 200
        mock_picker.assert_awaited_once_with(
            http.gphotos_picker,
            "fresh-token",
            max_item_count=50,
        )

    async def test_google_import_stream_emits_completion(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        users_dir = get_settings().USERS_FOLDER
        uid = await _signed_in_album(client, session, users_dir)
        await connect_google_photos(session, uid)

        http = _mock_http_clients()
        app.dependency_overrides[_get_http_clients] = lambda: http
        http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
            {"access_token": "fresh-token", "expires_in": 3600}
        )

        async def fake_download(**kwargs: object) -> AsyncIterator[SavedInput]:
            path = Path(kwargs["temp_dir"]) / "google-source"
            data = _jpeg_bytes()
            path.write_bytes(data)
            yield SavedInput(path=path, size=len(data))

        with (
            patch(
                "app.api.v1.routes.media_imports._validate_google_import_target",
                AsyncMock(),
            ),
            patch(
                "app.api.v1.routes.media_imports._download_google_items",
                fake_download,
            ),
            patch(
                "app.api.v1.routes.media_imports._persist_google_import",
                AsyncMock(
                    return_value=[
                        "11111111-1111-4111-8111-111111111111_"
                        "22222222-2222-4222-8222-222222222222.jpg"
                    ]
                ),
            ),
        ):
            resp = await client.post(
                f"/api/v1/albums/{AID}/media-imports/google",
                json={"context": "cover", "session_id": "session-abc"},
            )

        assert resp.status_code == 200
        assert "import_in_progress" in resp.text
        assert "import_completed" in resp.text
        assert ".jpg" in resp.text

    async def test_google_import_stream_reports_download_size_errors(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        users_dir = get_settings().USERS_FOLDER
        uid = await _signed_in_album(client, session, users_dir)
        await connect_google_photos(session, uid)

        http = _mock_http_clients()
        app.dependency_overrides[_get_http_clients] = lambda: http
        http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
            {"access_token": "fresh-token", "expires_in": 3600}
        )

        async def fail_download(**_kwargs: object) -> AsyncIterator[SavedInput]:
            async for item in _no_saved_inputs():
                yield item
            raise DownloadTooLargeError("Download exceeds 200 MB limit")

        with (
            patch(
                "app.api.v1.routes.media_imports._validate_google_import_target",
                AsyncMock(),
            ),
            patch(
                "app.api.v1.routes.media_imports._download_google_items",
                fail_download,
            ),
        ):
            resp = await client.post(
                f"/api/v1/albums/{AID}/media-imports/google",
                json={"context": "cover", "session_id": "session-abc"},
            )

        assert resp.status_code == 200
        assert "Download exceeds 200 MB limit" in resp.text
        assert "Media import failed unexpectedly." not in resp.text

    async def test_google_import_validates_step_before_download(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        users_dir = get_settings().USERS_FOLDER
        uid = await _signed_in_album(client, session, users_dir)
        await connect_google_photos(session, uid)

        http = _mock_http_clients()
        app.dependency_overrides[_get_http_clients] = lambda: http
        http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
            {"access_token": "fresh-token", "expires_in": 3600}
        )
        downloaded = False

        async def fake_download(**_kwargs: object) -> AsyncIterator[SavedInput]:
            nonlocal downloaded
            downloaded = True
            async for item in _no_saved_inputs():
                yield item

        with (
            patch(
                "app.api.v1.routes.media_imports._validate_google_import_target",
                AsyncMock(side_effect=ValueError("Step not found")),
            ),
            patch(
                "app.api.v1.routes.media_imports._download_google_items",
                fake_download,
            ),
        ):
            resp = await client.post(
                f"/api/v1/albums/{AID}/media-imports/google",
                json={"context": "step", "step_id": 999, "session_id": "session-abc"},
            )

        assert resp.status_code == 200
        assert "Step not found" in resp.text
        assert "Media import failed unexpectedly." not in resp.text
        assert not downloaded

    async def test_google_import_validation_returns_http_error_before_stream(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await _signed_in_album(client, session, get_settings().USERS_FOLDER)

        resp = await client.post(
            f"/api/v1/albums/{AID}/media-imports/google",
            json={"context": "cover", "session_id": "session-abc"},
        )

        assert resp.status_code == 400
        assert "text/event-stream" not in resp.headers.get("content-type", "")

    async def test_google_video_import_downloads_video_variant(
        self, tmp_path: Path
    ) -> None:
        http = _mock_http_clients()
        item = PickedMediaItem(
            id="video-1",
            create_time="2024-01-01T00:00:00Z",
            type="VIDEO",
            media_file=GoogleMediaFile(
                base_url="https://lh3.googleusercontent.com/video",
                mime_type="video/mp4",
                filename="video.mp4",
            ),
        )

        async def fake_download(*args: object, **kwargs: object) -> None:
            dest = args[3]
            assert isinstance(dest, Path)
            dest.write_bytes(b"video")

        with (
            patch(
                "app.api.v1.routes.media_imports.get_media_items",
                AsyncMock(return_value=[item]),
            ),
            patch(
                "app.api.v1.routes.media_imports.download_media_to_file",
                AsyncMock(side_effect=fake_download),
            ) as download,
        ):
            access = "fresh-token"
            saved = [
                item
                async for item in _download_google_items(
                    http=http,
                    access_token=access,
                    session_id="session-abc",
                    temp_dir=tmp_path,
                )
            ]

        assert len(saved) == 1
        assert download.await_args.kwargs["param"] == "=dv"


class TestPersistImportedMedia:
    async def test_import_one_cleans_current_video_on_cancellation(
        self, tmp_path: Path
    ) -> None:
        output = tmp_path / "imported.mp4"
        poster = tmp_path / "imported.jpg"

        def fake_generated_name(suffix: str) -> str:
            return f"imported{suffix}"

        async def cancel_video(_raw: Path, target: Path) -> None:
            await anyio.Path(target).write_bytes(b"video")
            await anyio.Path(poster).write_bytes(b"poster")
            raise asyncio.CancelledError

        with (
            patch("app.logic.media_import._process_photo", side_effect=OSError),
            patch("app.logic.media_import._generated_name", fake_generated_name),
            patch("app.logic.media_import.process_video", cancel_video),
            pytest.raises(asyncio.CancelledError),
        ):
            await _import_one(SavedInput(path=tmp_path / "raw", size=1), tmp_path)

        assert not output.exists()
        assert not poster.exists()

    async def test_process_saved_media_cleans_written_file_on_cancellation(
        self, tmp_path: Path
    ) -> None:
        output = tmp_path / "imported.jpg"
        output.write_bytes(b"imported")
        media = Media(name="imported.jpg", width=640, height=480)

        with (
            patch(
                "app.logic.media_import._import_one",
                AsyncMock(
                    side_effect=[
                        (media, output),
                        asyncio.CancelledError(),
                    ],
                ),
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await process_saved_media(
                album_dir=tmp_path,
                saved=[
                    SavedInput(path=tmp_path / "raw-1", size=1),
                    SavedInput(path=tmp_path / "raw-2", size=1),
                ],
            )

        assert not output.exists()

    async def test_import_saved_media_keeps_files_after_successful_persist(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = await _signed_in_album(client, session, get_settings().USERS_FOLDER)
        album = await session.get_one(Album, (uid, AID))
        output = tmp_path / "imported.jpg"
        output.write_bytes(b"imported")
        media = Media(name="imported.jpg", width=640, height=480)

        with (
            patch(
                "app.logic.media_import.process_saved_media",
                AsyncMock(return_value=([media], [output])),
            ),
            patch(
                "app.logic.media_import.persist_imported_media",
                AsyncMock(return_value=["imported.jpg"]),
            ),
        ):
            names = await import_saved_media(
                session,
                album=album,
                album_dir=tmp_path,
                request=ImportRequest(context="cover"),
                saved=[SavedInput(path=tmp_path / "raw", size=1)],
            )

        assert names == ["imported.jpg"]
        assert output.exists()

    async def test_import_saved_media_cleans_processed_file_on_cancellation(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = await _signed_in_album(client, session, get_settings().USERS_FOLDER)
        album = await session.get_one(Album, (uid, AID))
        output = tmp_path / "imported.jpg"
        output.write_bytes(b"imported")
        media = Media(name="imported.jpg", width=640, height=480)

        with (
            patch(
                "app.logic.media_import.process_saved_media",
                AsyncMock(return_value=([media], [output])),
            ),
            patch(
                "app.logic.media_import.persist_imported_media",
                AsyncMock(side_effect=asyncio.CancelledError()),
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await import_saved_media(
                session,
                album=album,
                album_dir=tmp_path,
                request=ImportRequest(context="cover"),
                saved=[SavedInput(path=tmp_path / "raw", size=1)],
            )

        assert not output.exists()

    async def test_refetches_album_before_appending_media(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        uid = await _signed_in_album(client, session, get_settings().USERS_FOLDER)
        stale_album = await session.get_one(Album, (uid, AID))

        with session.no_autoflush:
            session.add(
                AlbumMedia(
                    uid=uid,
                    aid=AID,
                    name="other.jpg",
                    kind="photo",
                    storage_path="other.jpg",
                    width=640,
                    height=480,
                    byte_size=1,
                    source_ref_id=None,
                )
            )
            await session.flush()

            imported = Media(name="imported.jpg", width=640, height=480)
            await persist_imported_media(
                session,
                album=stale_album,
                request=ImportRequest(context="cover"),
                imported=[imported],
            )

        media_rows = (
            await session.exec(
                select(AlbumMedia)
                .where(AlbumMedia.uid == uid, AlbumMedia.aid == AID)
                .order_by(col(AlbumMedia.created_at), col(AlbumMedia.name))
            )
        ).all()
        assert [row.name for row in media_rows][-2:] == ["other.jpg", "imported.jpg"]

    async def test_refetches_step_before_prepending_unused_media(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        uid = await _signed_in_album(client, session, get_settings().USERS_FOLDER)
        album = await session.get_one(Album, (uid, AID))

        with session.no_autoflush:
            stale_step = await session.get_one(Step, (uid, AID, 1))
            stale_step.unused = ["stale.jpg"]
            session.add(stale_step)
            await session.flush()

            fresh_step = await session.get_one(
                Step,
                (uid, AID, 1),
                populate_existing=True,
            )
            fresh_step.unused = ["concurrent.jpg"]
            session.add(fresh_step)
            await session.flush()

            imported = Media(name="imported.jpg", width=640, height=480)
            await persist_imported_media(
                session,
                album=album,
                request=ImportRequest(context="step", step_id=1),
                imported=[imported],
            )

        step = await session.get_one(Step, (uid, AID, 1), populate_existing=True)
        assert step.unused[:2] == ["imported.jpg", "concurrent.jpg"]

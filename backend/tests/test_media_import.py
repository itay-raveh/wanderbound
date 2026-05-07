from __future__ import annotations

import io
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from httpx_oauth.oauth2 import OAuth2Token
from PIL import Image
from pydantic import TypeAdapter

from app.api.v1.deps import _get_http_clients
from app.core.config import get_settings
from app.logic.layout.media import MediaName
from app.main import app
from app.models.album import Album
from app.models.step import Step

from .conftest import _mock_http_clients
from .factories import (
    AID,
    connect_google_photos,
    insert_album,
    insert_step,
    sign_in_and_upload,
)

if TYPE_CHECKING:
    from pathlib import Path

    from httpx import AsyncClient
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
    await insert_step(session, uid)
    album_dir = users_dir / str(uid) / "trip" / AID
    album_dir.mkdir(parents=True, exist_ok=True)
    await session.flush()
    return uid


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

        album = await session.get_one(Album, (uid, AID))
        assert [m.name for m in album.media][-2:] == imported

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
        assert album.media[-1].name == imported[0]

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


class TestGoogleMediaImport:
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

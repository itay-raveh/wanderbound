from __future__ import annotations

import io
from collections.abc import AsyncIterator
from inspect import signature
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from httpx_oauth.oauth2 import OAuth2Token
from PIL import Image

from app.api.v1.deps import _get_http_clients
from app.api.v1.routes.external_media import add_google_media
from app.core.http_clients import HttpClients
from app.main import app
from app.models.album_media import AlbumMedia, StepUnusedMedia
from app.models.google_photos import GoogleMediaFile, PickedMediaItem
from app.models.user import User

from .conftest import _mock_http_clients
from .factories import (
    AID,
    DEFAULT_MEDIA_NAME,
    MISSING_MEDIA_NAME,
    connect_google_photos,
    sign_in_with_album_media,
)

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


def _jpeg_bytes(width: int = 640, height: int = 480) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="red").save(buf, "JPEG")
    return buf.getvalue()


def _pin_http_clients() -> HttpClients:
    http = _mock_http_clients()
    app.dependency_overrides[_get_http_clients] = lambda: http
    return http


async def test_device_add_to_step_prepends_unused(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(client, session)

    resp = await client.post(
        f"/api/v1/albums/{AID}/external-media/add/device",
        data={"context": "step", "step_id": "1"},
        files=[("files", ("holiday.jpg", _jpeg_bytes(), "image/jpeg"))],
    )

    assert resp.status_code == 200
    imported = resp.json()["names"]
    assert len(imported) == 1

    unused = await session.get_one(StepUnusedMedia, (scenario.uid, AID, 1, 0))
    assert unused.media_name == imported[0]

    row = await session.get_one(AlbumMedia, (scenario.uid, AID, imported[0]))
    assert row.kind == "photo"
    assert row.upgrade_candidate is False
    assert row.byte_size > 0


def test_google_add_stream_route_does_not_depend_on_request_db_session() -> None:
    params = signature(add_google_media).parameters
    assert "session" not in params
    assert "user" not in params


async def test_device_add_to_cover_does_not_select_cover(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(client, session)

    resp = await client.post(
        f"/api/v1/albums/{AID}/external-media/add/device",
        data={"context": "cover"},
        files=[("files", ("cover.jpg", _jpeg_bytes(900, 600), "image/jpeg"))],
    )

    assert resp.status_code == 200
    imported = resp.json()["names"][0]
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, imported))
    assert row.width == 900
    assert row.height == 600


async def test_device_replace_updates_existing_media(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(
        client,
        session,
        write_media=True,
    )

    resp = await client.post(
        f"/api/v1/albums/{AID}/external-media/replace/device",
        data={"media_name": scenario.media_name},
        files={"file": ("replacement.jpg", _jpeg_bytes(1200, 800), "image/jpeg")},
    )

    assert resp.status_code == 200
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    assert row.width == 1200
    assert row.height == 800


async def test_device_replace_schedules_undo_snapshot_prune(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(
        client,
        session,
        write_media=True,
    )

    with patch(
        "app.api.v1.routes.external_media.enqueue_undo_snapshot_prune",
    ) as enqueue_prune:
        resp = await client.post(
            f"/api/v1/albums/{AID}/external-media/replace/device",
            data={"media_name": scenario.media_name},
            files={"file": ("replacement.jpg", _jpeg_bytes(1200, 800), "image/jpeg")},
        )

    assert resp.status_code == 200
    enqueue_prune.assert_called_once()
    _, scheduled_uid, scheduled_aid, scheduled_dir = enqueue_prune.call_args.args
    assert (scheduled_uid, scheduled_aid, scheduled_dir) == (
        scenario.uid,
        AID,
        scenario.album_dir,
    )


async def test_device_replace_oversized_upload_returns_413(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    await sign_in_with_album_media(client, session)

    with patch(
        "app.api.v1.routes.external_media.save_uploads",
        AsyncMock(side_effect=OverflowError("Import is too large")),
    ):
        resp = await client.post(
            f"/api/v1/albums/{AID}/external-media/replace/device",
            data={"media_name": DEFAULT_MEDIA_NAME},
            files={"file": ("replacement.jpg", b"too large", "image/jpeg")},
        )

    assert resp.status_code == 413
    assert resp.json()["detail"] == "Import is too large"


async def test_device_replace_missing_media_returns_404(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    await sign_in_with_album_media(client, session)
    save_uploads = AsyncMock(side_effect=AssertionError("should not save upload"))

    with patch("app.api.v1.routes.external_media.save_uploads", save_uploads):
        resp = await client.post(
            f"/api/v1/albums/{AID}/external-media/replace/device",
            data={"media_name": MISSING_MEDIA_NAME},
            files={"file": ("replacement.jpg", _jpeg_bytes(1200, 800), "image/jpeg")},
        )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Media not found"
    save_uploads.assert_not_awaited()


async def test_undo_replacement_restores_previous_dimensions(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(
        client,
        session,
        write_media=True,
    )

    replace_resp = await client.post(
        f"/api/v1/albums/{AID}/external-media/replace/device",
        data={"media_name": scenario.media_name},
        files={"file": ("replacement.jpg", _jpeg_bytes(1200, 800), "image/jpeg")},
    )
    assert replace_resp.status_code == 200

    undo_resp = await client.post(
        f"/api/v1/albums/{AID}/external-media/undo/{scenario.media_name}",
    )

    assert undo_resp.status_code == 200
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    assert row.width == 640
    assert row.height == 480


async def test_undo_after_repeated_replacement_restores_immediate_previous_file(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(
        client,
        session,
        write_media=True,
    )

    first_replace = await client.post(
        f"/api/v1/albums/{AID}/external-media/replace/device",
        data={"media_name": scenario.media_name},
        files={"file": ("replacement.jpg", _jpeg_bytes(1200, 800), "image/jpeg")},
    )
    assert first_replace.status_code == 200

    second_replace = await client.post(
        f"/api/v1/albums/{AID}/external-media/replace/device",
        data={"media_name": scenario.media_name},
        files={"file": ("replacement.jpg", _jpeg_bytes(1600, 900), "image/jpeg")},
    )
    assert second_replace.status_code == 200

    undo_resp = await client.post(
        f"/api/v1/albums/{AID}/external-media/undo/{scenario.media_name}",
    )

    assert undo_resp.status_code == 200
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    assert row.width == 1200
    assert row.height == 800


async def test_undo_replacement_restores_previous_upgrade_candidate(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(
        client,
        session,
        write_media=True,
    )
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    row.upgrade_candidate = True
    session.add(row)
    await session.commit()

    replace_resp = await client.post(
        f"/api/v1/albums/{AID}/external-media/replace/device",
        data={"media_name": scenario.media_name},
        files={"file": ("replacement.jpg", _jpeg_bytes(1200, 800), "image/jpeg")},
    )
    assert replace_resp.status_code == 200
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    assert row.upgrade_candidate is False

    undo_resp = await client.post(
        f"/api/v1/albums/{AID}/external-media/undo/{scenario.media_name}",
    )

    assert undo_resp.status_code == 200
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    assert row.upgrade_candidate is True


async def test_google_replace_requires_one_selected_item(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(client, session)
    await connect_google_photos(session, scenario.uid)

    http = _pin_http_clients()
    http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
        {"access_token": "fresh-token", "expires_in": 3600}
    )

    with patch(
        "app.logic.external_media.operations.get_media_items",
        AsyncMock(return_value=[]),
    ):
        resp = await client.post(
            f"/api/v1/albums/{AID}/external-media/replace/google",
            json={"media_name": DEFAULT_MEDIA_NAME, "session_id": "session-abc"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Select exactly one replacement"


async def test_google_replace_rejects_multiple_items_before_download(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(client, session)
    await connect_google_photos(session, scenario.uid)

    http = _pin_http_clients()
    http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
        {"access_token": "fresh-token", "expires_in": 3600}
    )
    items = [
        PickedMediaItem(
            id="google-1",
            create_time="2024-01-01T00:00:00Z",
            type="PHOTO",
            media_file=GoogleMediaFile(
                base_url="https://lh3.googleusercontent.com/one",
                mime_type="image/jpeg",
                filename="one.jpg",
                width=1200,
                height=800,
            ),
        ),
        PickedMediaItem(
            id="google-2",
            create_time="2024-01-02T00:00:00Z",
            type="PHOTO",
            media_file=GoogleMediaFile(
                base_url="https://lh3.googleusercontent.com/two",
                mime_type="image/jpeg",
                filename="two.jpg",
                width=1200,
                height=800,
            ),
        ),
    ]

    with (
        patch(
            "app.logic.external_media.operations.get_media_items",
            AsyncMock(return_value=items),
        ),
        patch(
            "app.logic.external_media.operations.download_media_to_file",
            AsyncMock(),
        ) as download,
    ):
        resp = await client.post(
            f"/api/v1/albums/{AID}/external-media/replace/google",
            json={"media_name": DEFAULT_MEDIA_NAME, "session_id": "session-abc"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Select exactly one replacement"
    download.assert_not_awaited()


async def test_google_add_validates_step_before_download(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(client, session)
    await connect_google_photos(session, scenario.uid)

    http = _pin_http_clients()
    http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
        {"access_token": "fresh-token", "expires_in": 3600}
    )
    downloaded = False

    async def fail_if_downloaded(**_kwargs: object) -> AsyncIterator[object]:
        nonlocal downloaded
        downloaded = True
        for item in ():
            yield item

    with (
        patch(
            "app.api.v1.routes.external_media.download_google_items_to_saved",
            fail_if_downloaded,
        ),
        patch("app.api.v1.routes.external_media.get_engine", return_value=session.bind),
    ):
        resp = await client.post(
            f"/api/v1/albums/{AID}/external-media/add/google",
            json={"context": "step", "step_id": 999, "session_id": "session-abc"},
        )

    assert resp.status_code == 200
    assert "Step not found" in resp.text
    assert not downloaded


async def test_google_add_collapses_lost_token_to_disconnected(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(client, session)
    await connect_google_photos(session, scenario.uid)
    user = await session.get_one(User, scenario.uid)
    user.google_photos_refresh_token = None
    session.add(user)
    await session.commit()

    with patch(
        "app.api.v1.routes.external_media.get_engine", return_value=session.bind
    ):
        resp = await client.post(
            f"/api/v1/albums/{AID}/external-media/add/google",
            json={"context": "cover", "session_id": "session-abc"},
        )

    assert resp.status_code == 400
    assert "Google Photos not connected" in resp.text
    await session.refresh(user)
    assert user.google_photos_connected_at is None


async def test_google_replace_validates_media_before_download(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(client, session)
    await connect_google_photos(session, scenario.uid)

    http = _pin_http_clients()
    http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
        {"access_token": "fresh-token", "expires_in": 3600}
    )
    downloaded = False

    async def fail_if_downloaded(**_kwargs: object) -> AsyncIterator[object]:
        nonlocal downloaded
        downloaded = True
        for item in ():
            yield item

    with patch(
        "app.api.v1.routes.external_media.download_google_items_to_saved",
        fail_if_downloaded,
    ):
        resp = await client.post(
            f"/api/v1/albums/{AID}/external-media/replace/google",
            json={"media_name": MISSING_MEDIA_NAME, "session_id": "session-abc"},
        )

    assert resp.status_code == 404
    assert not downloaded


async def test_google_replace_marks_media_upgraded(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    scenario = await sign_in_with_album_media(
        client,
        session,
        write_media=True,
    )
    await connect_google_photos(session, scenario.uid)

    http = _pin_http_clients()
    http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
        {"access_token": "fresh-token", "expires_in": 3600}
    )
    item = PickedMediaItem(
        id="google-1",
        create_time="2024-01-01T00:00:00Z",
        type="PHOTO",
        media_file=GoogleMediaFile(
            base_url="https://lh3.googleusercontent.com/test",
            mime_type="image/jpeg",
            filename="picked.jpg",
            width=1200,
            height=800,
        ),
    )

    async def fake_download(*args: object, **kwargs: object) -> None:
        dest = args[3]
        assert isinstance(dest, Path)
        dest.write_bytes(_jpeg_bytes(1200, 800))

    with (
        patch(
            "app.logic.external_media.operations.get_media_items",
            AsyncMock(return_value=[item]),
        ),
        patch(
            "app.logic.external_media.operations.download_media_to_file",
            AsyncMock(side_effect=fake_download),
        ),
    ):
        resp = await client.post(
            f"/api/v1/albums/{AID}/external-media/replace/google",
            json={"media_name": scenario.media_name, "session_id": "session-abc"},
        )

    assert resp.status_code == 200
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    assert row.upgrade_candidate is False

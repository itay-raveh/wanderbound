from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from httpx_oauth.oauth2 import OAuth2Token
from itsdangerous import URLSafeTimedSerializer

from app.api.v1.deps import _get_http_clients
from app.core.config import get_settings
from app.core.http_clients import HttpClients
from app.main import app
from app.models.google_photos import GoogleMediaFile, PickedMediaItem
from tests.conftest import _mock_http_clients
from tests.factories import (
    AlbumMediaScenario,
    connect_google_photos,
    sign_in_connected_google_photos,
    sign_in_with_album_media,
)

if TYPE_CHECKING:
    from httpx import AsyncClient, Response
    from sqlmodel.ext.asyncio.session import AsyncSession


def fresh_oauth_token() -> OAuth2Token:
    return OAuth2Token({"access_token": "fresh-token", "expires_in": 3600})


def pin_http_clients() -> HttpClients:
    http = _mock_http_clients()
    app.dependency_overrides[_get_http_clients] = lambda: http
    return http


async def connected_google_photos_http(
    client: AsyncClient, session: AsyncSession
) -> HttpClients:
    await sign_in_connected_google_photos(client, session)
    http = pin_http_clients()
    http.gphotos_oauth.refresh_token.return_value = fresh_oauth_token()
    return http


async def google_connected_album_media(
    client: AsyncClient,
    session: AsyncSession,
    *,
    write_media: bool = False,
) -> AlbumMediaScenario:
    scenario = await sign_in_with_album_media(
        client,
        session,
        write_media=write_media,
    )
    await connect_google_photos(session, scenario.uid)
    http = pin_http_clients()
    http.gphotos_oauth.refresh_token.return_value = fresh_oauth_token()
    return scenario


def picker_mock() -> AsyncMock:
    mock_picker = AsyncMock()
    mock_picker.return_value.id = "session-abc"
    mock_picker.return_value.picker_uri = "https://photos.google.com/picker/abc"
    return mock_picker


def picked_item(
    item_id: str = "google-1",
    *,
    filename: str = "picked.jpg",
    base_url: str = "https://lh3.googleusercontent.com/test",
    width: int = 1200,
    height: int = 800,
) -> PickedMediaItem:
    return PickedMediaItem(
        id=item_id,
        create_time="2024-01-01T00:00:00Z",
        type="PHOTO",
        media_file=GoogleMediaFile(
            base_url=base_url,
            mime_type="image/jpeg",
            filename=filename,
            width=width,
            height=height,
        ),
    )


def build_callback_state(
    csrf: str = "test-csrf-value",
    nonce: str = "n-8chars",
    redirect_uri: str = "http://test/api/v1/google-photos/callback",
) -> str:
    return URLSafeTimedSerializer(
        get_settings().SECRET_KEY, salt="gphotos-oauth-state"
    ).dumps({"csrf": csrf, "nonce": nonce, "redirect_uri": redirect_uri})


def build_oauth_cookie(
    csrf: str = "test-csrf-value",
    verifier: str = "test-verifier-value",
) -> str:
    return URLSafeTimedSerializer(
        get_settings().SECRET_KEY, salt="gphotos-oauth-cookie"
    ).dumps({"csrf": csrf, "verifier": verifier})


async def oauth_callback(
    client: AsyncClient,
    *,
    csrf: str = "test-csrf-value",
    cookie_csrf: str | None = "test-csrf-value",
    verifier: str = "test-verifier-value",
) -> Response:
    state = build_callback_state(csrf=csrf)
    if cookie_csrf is not None:
        client.cookies.set(
            "gphotos_oauth",
            build_oauth_cookie(csrf=cookie_csrf, verifier=verifier),
        )
    return await client.get(
        "/api/v1/google-photos/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )


def assert_error_redirect(resp: Response) -> None:
    assert resp.status_code == 303
    assert "?error" in resp.headers["location"]

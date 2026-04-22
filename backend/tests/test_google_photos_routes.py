"""Integration tests for Google Photos routes.

Tests auth gating, disconnect, and edge cases. The full upgrade flow
requires mocking the Google Picker API extensively, which is best tested
E2E. The matching algorithm is covered in test_media_upgrade.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx_oauth.oauth2 import (
    GetAccessTokenError,
    OAuth2Token,
    RefreshTokenError,
)
from itsdangerous import URLSafeTimedSerializer

from app.api.v1.deps import _get_http_clients
from app.api.v1.routes.google_photos import _validate_match_names
from app.core.config import get_settings
from app.core.http_clients import HttpClients
from app.logic.media_upgrade.phash_matching import MatchResult
from app.logic.media_upgrade.pipeline import _clear_caches
from app.main import app
from app.models.user import User

from .conftest import _mock_http_clients
from .factories import (
    connect_google_photos,
    sign_in_and_upload,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture(autouse=True)
def _clear_upgrade_caches_between_tests() -> Iterator[None]:
    """Reset the event-loop-bound semaphore cache between tests."""
    yield
    _clear_caches()


def _pin_http_clients() -> HttpClients:
    """Return (and install) a pinned HttpClients that survives across requests.

    The default conftest override constructs a fresh mock per request, which
    loses any state the test sets up. Pin one instance so configuring
    ``http.gphotos_oauth.*`` is visible to the route handler.
    """
    http = _mock_http_clients()
    app.dependency_overrides[_get_http_clients] = lambda: http
    return http


def _build_callback_state(
    csrf: str = "test-csrf-value",
    nonce: str = "n-8chars",
    redirect_uri: str = "http://test/api/v1/google-photos/callback",
) -> str:
    return URLSafeTimedSerializer(
        get_settings().SECRET_KEY, salt="gphotos-oauth-state"
    ).dumps({"csrf": csrf, "nonce": nonce, "redirect_uri": redirect_uri})


def _build_oauth_cookie(
    csrf: str = "test-csrf-value",
    verifier: str = "test-verifier-value",
) -> str:
    return URLSafeTimedSerializer(
        get_settings().SECRET_KEY, salt="gphotos-oauth-cookie"
    ).dumps({"csrf": csrf, "verifier": verifier})


class TestRequireGoogleUser:
    async def test_microsoft_user_gets_403(self, client: AsyncClient) -> None:
        """Microsoft-authed users cannot access Google Photos endpoints."""
        users_dir = get_settings().USERS_FOLDER
        users_dir.mkdir(parents=True, exist_ok=True)

        await sign_in_and_upload(client, users_dir, provider="microsoft")
        resp = await client.post("/api/v1/google-photos/sessions")
        assert resp.status_code == 403

    async def test_google_user_without_connection_gets_400(
        self, client: AsyncClient
    ) -> None:
        """Google user without Photos connected gets 400 on session create."""
        users_dir = get_settings().USERS_FOLDER
        users_dir.mkdir(parents=True, exist_ok=True)

        await sign_in_and_upload(client, users_dir, provider="google")
        resp = await client.post("/api/v1/google-photos/sessions")
        assert resp.status_code == 400


class TestDisconnect:
    async def test_disconnect_clears_tokens(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        users_dir = get_settings().USERS_FOLDER
        users_dir.mkdir(parents=True, exist_ok=True)

        user_data = await sign_in_and_upload(client, users_dir, provider="google")
        uid = user_data["id"]

        await connect_google_photos(session, uid)
        _pin_http_clients()  # disconnect calls revoke_token on the mock

        resp = await client.delete("/api/v1/google-photos/connection")
        assert resp.status_code == 204

        user = await session.get(User, uid)
        assert user is not None
        assert user.google_photos_refresh_token is None
        assert user.google_photos_connected_at is None


class TestPickerSession:
    async def test_create_session_calls_google_api(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        users_dir = get_settings().USERS_FOLDER
        users_dir.mkdir(parents=True, exist_ok=True)

        user_data = await sign_in_and_upload(client, users_dir, provider="google")
        uid = user_data["id"]
        await connect_google_photos(session, uid)

        http = _pin_http_clients()
        http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
            {"access_token": "fresh-token", "expires_in": 3600}
        )
        mock_picker = AsyncMock()
        mock_picker.return_value.id = "session-abc"
        mock_picker.return_value.picker_uri = "https://photos.google.com/picker/abc"

        with patch(
            "app.api.v1.routes.google_photos.create_picker_session",
            mock_picker,
        ):
            resp = await client.post("/api/v1/google-photos/sessions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "session-abc"
        assert "picker" in data["picker_uri"]


class TestValidateMatchNames:
    def test_accepts_valid_names(self) -> None:
        matches = [MatchResult(local_name="photo1.jpg", google_id="gid-1", distance=0)]
        _validate_match_names(matches, {"photo1.jpg", "photo2.jpg"})

    def test_rejects_unknown_name(self) -> None:
        matches = [MatchResult(local_name="unknown.jpg", google_id="gid-1", distance=0)]
        with pytest.raises(HTTPException) as exc_info:
            _validate_match_names(matches, {"photo1.jpg"})
        assert exc_info.value.status_code == 422

    def test_rejects_if_any_name_invalid(self) -> None:
        matches = [
            MatchResult(local_name="photo1.jpg", google_id="gid-1", distance=0),
            MatchResult(local_name="evil.jpg", google_id="gid-2", distance=0),
        ]
        with pytest.raises(HTTPException) as exc_info:
            _validate_match_names(matches, {"photo1.jpg"})
        assert exc_info.value.status_code == 422
        assert "evil.jpg" in str(exc_info.value.detail)


class TestOAuthCallback:
    async def test_success_stores_refresh_token(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        users_dir = get_settings().USERS_FOLDER
        users_dir.mkdir(parents=True, exist_ok=True)

        user_data = await sign_in_and_upload(client, users_dir, provider="google")
        uid = user_data["id"]

        http = _pin_http_clients()
        http.gphotos_oauth.get_access_token.return_value = OAuth2Token(
            {"refresh_token": "rt-new-123", "access_token": "at-xyz"}
        )

        csrf = "test-csrf-value"
        state = _build_callback_state(csrf=csrf)
        client.cookies.set("gphotos_oauth", _build_oauth_cookie(csrf=csrf))
        resp = await client.get(
            "/api/v1/google-photos/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert "?error" not in resp.headers["location"]

        user = await session.get(User, uid)
        assert user is not None
        assert user.google_photos_refresh_token is not None
        assert user.google_photos_connected_at is not None

    async def test_oauth_error_redirects_with_error(self, client: AsyncClient) -> None:
        users_dir = get_settings().USERS_FOLDER
        users_dir.mkdir(parents=True, exist_ok=True)

        await sign_in_and_upload(client, users_dir, provider="google")

        http = _pin_http_clients()
        http.gphotos_oauth.get_access_token.side_effect = GetAccessTokenError(
            "access_denied"
        )

        csrf = "test-csrf-value"
        state = _build_callback_state(csrf=csrf)
        client.cookies.set("gphotos_oauth", _build_oauth_cookie(csrf=csrf))
        resp = await client.get(
            "/api/v1/google-photos/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert "?error" in resp.headers["location"]

    async def test_no_refresh_token_redirects_with_error(
        self, client: AsyncClient
    ) -> None:
        users_dir = get_settings().USERS_FOLDER
        users_dir.mkdir(parents=True, exist_ok=True)

        await sign_in_and_upload(client, users_dir, provider="google")

        http = _pin_http_clients()
        http.gphotos_oauth.get_access_token.return_value = OAuth2Token(
            {"access_token": "at-xyz"}  # no refresh_token
        )

        csrf = "test-csrf-value"
        state = _build_callback_state(csrf=csrf)
        client.cookies.set("gphotos_oauth", _build_oauth_cookie(csrf=csrf))
        resp = await client.get(
            "/api/v1/google-photos/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert "?error" in resp.headers["location"]

    async def test_state_csrf_mismatch_redirects_with_error(
        self, client: AsyncClient
    ) -> None:
        """Regression: cookie CSRF that disagrees with the signed state is rejected.

        This is the guarantee of the double-submit pattern - catches an
        attacker who can forge the state query param but cannot plant the
        matching HttpOnly cookie.
        """
        users_dir = get_settings().USERS_FOLDER
        users_dir.mkdir(parents=True, exist_ok=True)

        await sign_in_and_upload(client, users_dir, provider="google")

        client.cookies.set("gphotos_oauth", _build_oauth_cookie(csrf="cookie-csrf-A"))
        state = _build_callback_state(csrf="state-csrf-B")  # mismatched
        resp = await client.get(
            "/api/v1/google-photos/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert "?error" in resp.headers["location"]

    async def test_passes_pkce_verifier_to_token_exchange(
        self, client: AsyncClient
    ) -> None:
        """Regression: the cookie's PKCE verifier is forwarded to Google.

        Without this, the authorize-side code_challenge has no counterpart
        at token exchange and Google rejects the flow.
        """
        users_dir = get_settings().USERS_FOLDER
        users_dir.mkdir(parents=True, exist_ok=True)

        await sign_in_and_upload(client, users_dir, provider="google")

        http = _pin_http_clients()
        http.gphotos_oauth.get_access_token.return_value = OAuth2Token(
            {"refresh_token": "rt-x", "access_token": "at-x"}
        )

        csrf = "test-csrf-value"
        verifier = "test-verifier-value"
        state = _build_callback_state(csrf=csrf)
        client.cookies.set(
            "gphotos_oauth", _build_oauth_cookie(csrf=csrf, verifier=verifier)
        )
        await client.get(
            "/api/v1/google-photos/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

        http.gphotos_oauth.get_access_token.assert_awaited_once()
        call = http.gphotos_oauth.get_access_token.call_args
        assert call.kwargs.get("code_verifier") == verifier


class TestTokenRevocation:
    async def test_expired_token_returns_401(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """User with revoked token gets 401 on session create."""
        users_dir = get_settings().USERS_FOLDER
        users_dir.mkdir(parents=True, exist_ok=True)

        user_data = await sign_in_and_upload(client, users_dir, provider="google")
        uid = user_data["id"]
        await connect_google_photos(session, uid)

        http = _pin_http_clients()
        http.gphotos_oauth.refresh_token.side_effect = RefreshTokenError(
            "invalid_grant"
        )

        resp = await client.post("/api/v1/google-photos/sessions")

        assert resp.status_code == 401


class TestTokenLostSelfHeal:
    async def test_token_lost_collapses_to_disconnected(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """Regression: connected_at set + refresh_token=None heals to disconnected.

        Happens when SECRET_KEY rotates and EncryptedString can no longer
        decrypt the stored ciphertext. The self-heal lives in ``_get_user``
        so any authed request collapses the state at a single point.
        """
        users_dir = get_settings().USERS_FOLDER
        users_dir.mkdir(parents=True, exist_ok=True)

        user_data = await sign_in_and_upload(client, users_dir, provider="google")
        uid = user_data["id"]
        await connect_google_photos(session, uid)

        user = await session.get(User, uid)
        assert user is not None
        user.google_photos_refresh_token = None
        session.add(user)
        await session.flush()

        resp = await client.get("/api/v1/users")
        assert resp.status_code == 200
        assert resp.json()["google_photos_connected_at"] is None

        await session.refresh(user)
        assert user.google_photos_connected_at is None

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
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
from app.api.v1.routes.google_photos import _validate_match_names, match_media
from app.core.config import get_settings
from app.core.http_clients import HttpClients
from app.logic.media_upgrade.phash_matching import MatchResult
from app.logic.media_upgrade.pipeline import MatchCompleted, _clear_caches
from app.main import app
from app.models.polarsteps import Location
from app.models.step import StepRead
from app.models.user import User
from app.models.weather import Weather, WeatherData

from .conftest import _mock_http_clients
from .factories import (
    sign_in_connected_google_photos,
    sign_in_uploaded_user,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient, Response
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture(autouse=True)
def _clear_upgrade_caches_between_tests() -> Iterator[None]:
    yield
    _clear_caches()


def _pin_http_clients() -> HttpClients:
    http = _mock_http_clients()
    app.dependency_overrides[_get_http_clients] = lambda: http
    return http


async def _connected_google_photos_http(
    client: AsyncClient, session: AsyncSession
) -> HttpClients:
    await sign_in_connected_google_photos(client, session)
    http = _pin_http_clients()
    http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
        {"access_token": "fresh-token", "expires_in": 3600}
    )
    return http


def _picker_mock() -> AsyncMock:
    mock_picker = AsyncMock()
    mock_picker.return_value.id = "session-abc"
    mock_picker.return_value.picker_uri = "https://photos.google.com/picker/abc"
    return mock_picker


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


async def _oauth_callback(
    client: AsyncClient,
    *,
    csrf: str = "test-csrf-value",
    cookie_csrf: str | None = "test-csrf-value",
    verifier: str = "test-verifier-value",
) -> Response:
    state = _build_callback_state(csrf=csrf)
    if cookie_csrf is not None:
        client.cookies.set(
            "gphotos_oauth",
            _build_oauth_cookie(csrf=cookie_csrf, verifier=verifier),
        )
    return await client.get(
        "/api/v1/google-photos/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )


def _assert_error_redirect(resp: Response) -> None:
    assert resp.status_code == 303
    assert "?error" in resp.headers["location"]


class TestRequireGoogleUser:
    async def test_microsoft_user_gets_403(self, client: AsyncClient) -> None:
        await sign_in_uploaded_user(client, provider="microsoft")
        resp = await client.post("/api/v1/google-photos/sessions")
        assert resp.status_code == 403

    async def test_google_user_without_connection_gets_400(
        self, client: AsyncClient
    ) -> None:
        await sign_in_uploaded_user(client)
        resp = await client.post("/api/v1/google-photos/sessions")
        assert resp.status_code == 400


class TestDisconnect:
    async def test_disconnect_clears_tokens(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        uid = await sign_in_connected_google_photos(client, session)
        _pin_http_clients()

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
        await _connected_google_photos_http(client, session)
        mock_picker = _picker_mock()

        with patch(
            "app.api.v1.routes.google_photos.create_picker_session",
            mock_picker,
        ):
            resp = await client.post("/api/v1/google-photos/sessions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "session-abc"
        assert "picker" in data["picker_uri"]

    async def test_create_session_passes_picker_item_limit(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        http = await _connected_google_photos_http(client, session)
        mock_picker = _picker_mock()

        with patch(
            "app.api.v1.routes.google_photos.create_picker_session",
            mock_picker,
        ):
            resp = await client.post("/api/v1/google-photos/sessions?max_item_count=1")

        assert resp.status_code == 200
        mock_picker.assert_awaited_once_with(
            http.gphotos_picker,
            "fresh-token",
            max_item_count=1,
        )


class TestValidateMatchNames:
    def test_accepts_valid_names(self) -> None:
        matches = [MatchResult(local_name="photo1.jpg", google_id="gid-1", distance=0)]
        _validate_match_names(matches, {"photo1.jpg", "photo2.jpg"})

    @pytest.mark.parametrize(
        ("matches", "detail"),
        [
            (
                [MatchResult(local_name="unknown.jpg", google_id="gid-1", distance=0)],
                "unknown.jpg",
            ),
            (
                [
                    MatchResult(local_name="photo1.jpg", google_id="gid-1", distance=0),
                    MatchResult(local_name="evil.jpg", google_id="gid-2", distance=0),
                ],
                "evil.jpg",
            ),
        ],
    )
    def test_rejects_unknown_name(
        self, matches: list[MatchResult], detail: str
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            _validate_match_names(matches, {"photo1.jpg"})
        assert exc_info.value.status_code == 422
        assert detail in str(exc_info.value.detail)


class TestMatchMedia:
    async def test_keeps_non_candidate_media_in_match_set(self) -> None:
        user = User(
            id=1,
            first_name="Test",
            locale="en-US",
            unit_is_km=True,
            temperature_is_celsius=True,
            google_sub="sub",
            google_photos_refresh_token="refresh-token",  # noqa: S106
            google_photos_connected_at=datetime.now(UTC),
        )
        step = StepRead(
            uid=1,
            aid="trip-1",
            id=7,
            name="Step",
            description="",
            timestamp=1_700_000_000.0,
            timezone_id="UTC",
            location=Location(
                name="Place", detail="", country_code="nl", lat=52.0, lon=4.0
            ),
            elevation=0,
            weather=Weather(
                day=WeatherData(temp=20.0, feels_like=18.0, icon="clear"),
                night=None,
            ),
            cover=None,
            pages=[["photo.jpg"]],
            unused=[],
        )
        http = _mock_http_clients()
        http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
            {"access_token": "fresh-token", "expires_in": 3600}
        )
        captured: dict[str, object] = {}

        async def fake_run_matching(
            *_args: object, **kwargs: object
        ) -> AsyncIterator[MatchCompleted]:
            captured.update(kwargs)
            yield MatchCompleted(total_picked=0, matched=0, unmatched=0, matches=[])

        class FakeLock:
            async def __aenter__(self) -> bool:
                return True

            async def __aexit__(self, *_args: object) -> None:
                return None

        with (
            patch(
                "app.api.v1.routes.google_photos._snapshot_steps_and_upgrade_state",
                AsyncMock(return_value=([step], set())),
            ),
            patch(
                "app.api.v1.routes.google_photos.get_media_items",
                AsyncMock(return_value=[]),
            ),
            patch("app.api.v1.routes.google_photos.run_matching", fake_run_matching),
            patch(
                "app.api.v1.routes.google_photos.try_advisory_lock",
                return_value=FakeLock(),
            ),
        ):
            events = [event async for event in match_media("trip-1", user, http, "s1")]

        assert isinstance(events[-1], MatchCompleted)
        assert captured["media_by_step"] == {7: ["photo.jpg"]}
        assert captured["upgrade_candidates"] == set()


class TestOAuthCallback:
    async def test_success_stores_refresh_token(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user_data = await sign_in_uploaded_user(client)
        uid = user_data["id"]

        http = _pin_http_clients()
        http.gphotos_oauth.get_access_token.return_value = OAuth2Token(
            {"refresh_token": "rt-new-123", "access_token": "at-xyz"}
        )

        resp = await _oauth_callback(client)

        assert resp.status_code == 303
        assert "?error" not in resp.headers["location"]

        user = await session.get(User, uid)
        assert user is not None
        assert user.google_photos_refresh_token is not None
        assert user.google_photos_connected_at is not None

    @pytest.mark.parametrize(
        ("token", "side_effect"),
        [
            (None, GetAccessTokenError("access_denied")),
            (OAuth2Token({"access_token": "at-xyz"}), None),
        ],
    )
    async def test_token_exchange_failure_redirects_with_error(
        self,
        client: AsyncClient,
        token: OAuth2Token | None,
        side_effect: Exception | None,
    ) -> None:
        await sign_in_uploaded_user(client)

        http = _pin_http_clients()
        if side_effect is None:
            http.gphotos_oauth.get_access_token.return_value = token
        else:
            http.gphotos_oauth.get_access_token.side_effect = side_effect

        resp = await _oauth_callback(client)

        _assert_error_redirect(resp)

    async def test_state_csrf_mismatch_redirects_with_error(
        self, client: AsyncClient
    ) -> None:
        await sign_in_uploaded_user(client)

        resp = await _oauth_callback(
            client, csrf="state-csrf-B", cookie_csrf="cookie-csrf-A"
        )

        _assert_error_redirect(resp)

    async def test_passes_pkce_verifier_to_token_exchange(
        self, client: AsyncClient
    ) -> None:
        await sign_in_uploaded_user(client)

        http = _pin_http_clients()
        http.gphotos_oauth.get_access_token.return_value = OAuth2Token(
            {"refresh_token": "rt-x", "access_token": "at-x"}
        )

        verifier = "test-verifier-value"
        await _oauth_callback(client, verifier=verifier)

        http.gphotos_oauth.get_access_token.assert_awaited_once()
        call = http.gphotos_oauth.get_access_token.call_args
        assert call.kwargs.get("code_verifier") == verifier


class TestTokenRevocation:
    async def test_expired_token_returns_401(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        http = await _connected_google_photos_http(client, session)
        http.gphotos_oauth.refresh_token.side_effect = RefreshTokenError(
            "invalid_grant"
        )

        resp = await client.post("/api/v1/google-photos/sessions")

        assert resp.status_code == 401


class TestTokenLostSelfHeal:
    async def test_token_lost_collapses_to_disconnected(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        uid = await sign_in_connected_google_photos(client, session)

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

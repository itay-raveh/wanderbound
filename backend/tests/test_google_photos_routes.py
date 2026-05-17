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

from app.api.v1.routes.google_photos import _validate_match_names, match_media
from app.logic.media_upgrade.phash_matching import MatchResult
from app.logic.media_upgrade.pipeline import MatchCompleted, _clear_caches
from app.models.polarsteps import Location
from app.models.step import StepRead
from app.models.user import User
from app.models.weather import Weather, WeatherData

from .factories import (
    sign_in_connected_google_photos,
    sign_in_uploaded_user,
)
from .helpers.google_photos import (
    GooglePhotosRoutes,
    assert_error_redirect,
    connected_google_photos_http,
    oauth_callback,
    picker_mock,
    pin_http_clients,
)
from .helpers.users import UserRoutes

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture(autouse=True)
def _clear_upgrade_caches_between_tests() -> Iterator[None]:
    yield
    _clear_caches()


class TestRequireGoogleUser:
    async def test_microsoft_user_gets_403(
        self, client: AsyncClient, google_photos_routes: GooglePhotosRoutes
    ) -> None:
        await sign_in_uploaded_user(client, provider="microsoft")
        resp = await google_photos_routes.create_session()
        assert resp.status_code == 403

    async def test_google_user_without_connection_gets_400(
        self, client: AsyncClient, google_photos_routes: GooglePhotosRoutes
    ) -> None:
        await sign_in_uploaded_user(client)
        resp = await google_photos_routes.create_session()
        assert resp.status_code == 400


class TestDisconnect:
    async def test_disconnect_clears_tokens(
        self,
        client: AsyncClient,
        session: AsyncSession,
        google_photos_routes: GooglePhotosRoutes,
    ) -> None:
        uid = await sign_in_connected_google_photos(client, session)
        pin_http_clients()

        resp = await google_photos_routes.disconnect()
        assert resp.status_code == 204

        user = await session.get(User, uid)
        assert user is not None
        assert user.google_photos_refresh_token is None
        assert user.google_photos_connected_at is None


class TestPickerSession:
    async def test_create_session_calls_google_api(
        self,
        client: AsyncClient,
        session: AsyncSession,
        google_photos_routes: GooglePhotosRoutes,
    ) -> None:
        await connected_google_photos_http(client, session)
        mock_picker = picker_mock()

        with patch(
            "app.api.v1.routes.google_photos.create_picker_session",
            mock_picker,
        ):
            resp = await google_photos_routes.create_session()

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "session-abc"
        assert "picker" in data["picker_uri"]

    async def test_create_session_passes_picker_item_limit(
        self,
        client: AsyncClient,
        session: AsyncSession,
        google_photos_routes: GooglePhotosRoutes,
    ) -> None:
        http = await connected_google_photos_http(client, session)
        mock_picker = picker_mock()

        with patch(
            "app.api.v1.routes.google_photos.create_picker_session",
            mock_picker,
        ):
            resp = await google_photos_routes.create_session(max_item_count=1)

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
        http = pin_http_clients()
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

        http = pin_http_clients()
        http.gphotos_oauth.get_access_token.return_value = OAuth2Token(
            {"refresh_token": "rt-new-123", "access_token": "at-xyz"}
        )

        resp = await oauth_callback(client)

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

        http = pin_http_clients()
        if side_effect is None:
            http.gphotos_oauth.get_access_token.return_value = token
        else:
            http.gphotos_oauth.get_access_token.side_effect = side_effect

        resp = await oauth_callback(client)

        assert_error_redirect(resp)

    async def test_state_csrf_mismatch_redirects_with_error(
        self, client: AsyncClient
    ) -> None:
        await sign_in_uploaded_user(client)

        resp = await oauth_callback(
            client, csrf="state-csrf-B", cookie_csrf="cookie-csrf-A"
        )

        assert_error_redirect(resp)

    async def test_passes_pkce_verifier_to_token_exchange(
        self, client: AsyncClient
    ) -> None:
        await sign_in_uploaded_user(client)

        http = pin_http_clients()
        http.gphotos_oauth.get_access_token.return_value = OAuth2Token(
            {"refresh_token": "rt-x", "access_token": "at-x"}
        )

        verifier = "test-verifier-value"
        await oauth_callback(client, verifier=verifier)

        http.gphotos_oauth.get_access_token.assert_awaited_once()
        call = http.gphotos_oauth.get_access_token.call_args
        assert call.kwargs.get("code_verifier") == verifier


class TestTokenRevocation:
    async def test_expired_token_returns_401(
        self,
        client: AsyncClient,
        session: AsyncSession,
        google_photos_routes: GooglePhotosRoutes,
    ) -> None:
        http = await connected_google_photos_http(client, session)
        http.gphotos_oauth.refresh_token.side_effect = RefreshTokenError(
            "invalid_grant"
        )

        resp = await google_photos_routes.create_session()

        assert resp.status_code == 401


class TestTokenLostSelfHeal:
    async def test_token_lost_collapses_to_disconnected(
        self,
        client: AsyncClient,
        session: AsyncSession,
        user_routes: UserRoutes,
    ) -> None:
        uid = await sign_in_connected_google_photos(client, session)

        user = await session.get(User, uid)
        assert user is not None
        user.google_photos_refresh_token = None
        session.add(user)
        await session.flush()

        resp = await user_routes.current()
        assert resp.status_code == 200
        assert resp.json()["google_photos_connected_at"] is None

        await session.refresh(user)
        assert user.google_photos_connected_at is None

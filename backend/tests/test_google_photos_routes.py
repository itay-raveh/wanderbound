from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import HTTPStatusError, Request, Response
from httpx_oauth.oauth2 import (
    GetAccessTokenError,
    OAuth2Token,
    RefreshTokenError,
)
from sqlmodel import select

from app.api.v1.routes.google_photos import (
    UpgradeRequest,
    _validate_match_names,
    match_media,
    upgrade_media,
)
from app.logic.media_upgrade.phash_matching import MatchResult
from app.logic.media_upgrade.pipeline import (
    UpgradeCompleted,
    UpgradeFailed,
    _clear_caches,
)
from app.models.user import User
from app.services.google_photos import _clear_media_items_cache

from .factories import (
    make_user,
    sign_in_connected_google_photos,
    sign_in_uploaded_user,
)
from .helpers.google_photos import (
    GooglePhotosRoutes,
    assert_error_redirect,
    connected_google_photos_http,
    oauth_callback,
    picked_item,
    pin_http_clients,
)
from .helpers.users import UserRoutes

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


@asynccontextmanager
async def _acquired_lock() -> AsyncIterator[bool]:
    yield True


@pytest.fixture(autouse=True)
def _clear_upgrade_caches_between_tests() -> Iterator[None]:
    _clear_media_items_cache()
    yield
    _clear_caches()
    _clear_media_items_cache()


class TestRequireGoogleUser:
    async def test_microsoft_user_gets_403(
        self,
        client: AsyncClient,
        session: AsyncSession,
        google_photos_routes: GooglePhotosRoutes,
    ) -> None:
        await sign_in_uploaded_user(client, session, provider="microsoft")
        resp = await google_photos_routes.create_session()
        assert resp.status_code == 403

    @pytest.mark.usefixtures("uploaded_user")
    async def test_google_user_without_connection_gets_400(
        self, google_photos_routes: GooglePhotosRoutes
    ) -> None:
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


class TestValidateMatchNames:
    def test_rejects_unknown_name(self) -> None:
        matches = [MatchResult(local_name="unknown.jpg", google_id="gid-1", distance=0)]
        with pytest.raises(HTTPException) as exc_info:
            _validate_match_names(matches, {"photo1.jpg"})
        assert exc_info.value.status_code == 422
        assert "unknown.jpg" in str(exc_info.value.detail)


class TestMatchMedia:
    async def test_expired_picker_session_reports_selection_expired(self) -> None:
        user = make_user(1, google_sub="sub")
        user.google_photos_refresh_token = "refresh-token"  # noqa: S105
        user.google_photos_connected_at = datetime.now(UTC)
        http = pin_http_clients()
        http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
            {"access_token": "fresh-token", "expires_in": 3600}
        )
        request = Request("GET", "https://photospicker.googleapis.com/v1/mediaItems")
        response = Response(404, request=request)

        with (
            patch(
                "app.api.v1.routes.google_photos._snapshot_steps_and_upgrade_state",
                AsyncMock(return_value=([], set(), {})),
            ),
            patch(
                "app.api.v1.routes.google_photos.get_media_items_cached",
                AsyncMock(
                    side_effect=HTTPStatusError(
                        "not found", request=request, response=response
                    )
                ),
            ),
            patch(
                "app.api.v1.routes.google_photos.try_advisory_lock",
                return_value=_acquired_lock(),
            ),
        ):
            events = [event async for event in match_media("trip-1", user, http, "s1")]

        assert events == [UpgradeFailed(detail="selectionExpired")]

    async def test_token_refresh_failure_ends_stream_with_failure(self) -> None:
        user = make_user(1, google_sub="sub")
        user.google_photos_refresh_token = "refresh-token"  # noqa: S105
        user.google_photos_connected_at = datetime.now(UTC)
        http = pin_http_clients()
        http.gphotos_oauth.refresh_token.side_effect = RefreshTokenError("timeout")

        with patch(
            "app.api.v1.routes.google_photos.try_advisory_lock",
            return_value=_acquired_lock(),
        ):
            events = [event async for event in match_media("trip-1", user, http, "s1")]

        assert events == [UpgradeFailed(detail="Matching failed unexpectedly.")]


class TestUpgradeMedia:
    async def test_expired_picker_session_reports_selection_expired(self) -> None:
        user = make_user(1, google_sub="sub")
        user.google_photos_refresh_token = "refresh-token"  # noqa: S105
        user.google_photos_connected_at = datetime.now(UTC)
        http = pin_http_clients()
        http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
            {"access_token": "fresh-token", "expires_in": 3600}
        )
        request = Request("GET", "https://photospicker.googleapis.com/v1/mediaItems")
        response = Response(404, request=request)

        with (
            patch(
                "app.api.v1.routes.google_photos._snapshot_upgrade_state",
                AsyncMock(return_value=({}, set())),
            ),
            patch(
                "app.api.v1.routes.google_photos.get_media_items_cached",
                AsyncMock(
                    side_effect=HTTPStatusError(
                        "not found", request=request, response=response
                    )
                ),
            ),
            patch(
                "app.api.v1.routes.google_photos.try_advisory_lock",
                return_value=_acquired_lock(),
            ),
        ):
            events = [
                event
                async for event in upgrade_media(
                    "trip-1",
                    UpgradeRequest(session_ids=["s1"], matches=[]),
                    user,
                    http,
                )
            ]

        assert events == [UpgradeFailed(detail="selectionExpired")]

    async def test_token_refresh_failure_ends_stream_with_failure(self) -> None:
        user = make_user(1, google_sub="sub")
        user.google_photos_refresh_token = "refresh-token"  # noqa: S105
        user.google_photos_connected_at = datetime.now(UTC)
        http = pin_http_clients()
        http.gphotos_oauth.refresh_token.side_effect = RefreshTokenError("timeout")

        with (
            patch(
                "app.api.v1.routes.google_photos._snapshot_upgrade_state",
                AsyncMock(return_value=({}, set())),
            ),
            patch(
                "app.api.v1.routes.google_photos.try_advisory_lock",
                return_value=_acquired_lock(),
            ),
        ):
            events = [
                event
                async for event in upgrade_media(
                    "trip-1",
                    UpgradeRequest(session_ids=["s1"], matches=[]),
                    user,
                    http,
                )
            ]

        assert events == [UpgradeFailed(detail="Upgrade failed unexpectedly.")]

    async def test_passes_snapshot_dimensions_to_upgrade_pipeline(self) -> None:
        user = make_user(1, google_sub="sub")
        user.google_photos_refresh_token = "refresh-token"  # noqa: S105
        user.google_photos_connected_at = datetime.now(UTC)
        http = pin_http_clients()
        http.gphotos_oauth.refresh_token.return_value = OAuth2Token(
            {"access_token": "fresh-token", "expires_in": 3600}
        )
        match = MatchResult(
            local_name="photo.jpg", google_id="google-photo", distance=0
        )
        video_match = MatchResult(
            local_name="video.mp4", google_id="google-video", distance=0
        )
        captured: dict[str, object] = {}

        async def fake_run_upgrade(**kwargs: object) -> AsyncIterator[UpgradeCompleted]:
            captured.update(kwargs)
            yield UpgradeCompleted(replaced=0, skipped=1, failed=0)

        with (
            patch(
                "app.api.v1.routes.google_photos._snapshot_upgrade_state",
                AsyncMock(
                    return_value=(
                        {"photo.jpg": (1200, 800)},
                        {"photo.jpg"},
                    )
                ),
            ),
            patch(
                "app.api.v1.routes.google_photos.get_media_items_cached",
                AsyncMock(return_value=[picked_item("google-photo")]),
            ),
            patch("app.api.v1.routes.google_photos.run_upgrade", fake_run_upgrade),
            patch(
                "app.api.v1.routes.google_photos.try_advisory_lock",
                return_value=_acquired_lock(),
            ),
        ):
            events = [
                event
                async for event in upgrade_media(
                    "trip-1",
                    UpgradeRequest(session_ids=["s1"], matches=[match, video_match]),
                    user,
                    http,
                )
            ]

        assert events[-1] == UpgradeCompleted(replaced=0, skipped=1, failed=0)
        assert captured["local_dimensions"] == {"photo.jpg": (1200, 800)}
        assert captured["matches"] == [match]


class TestOAuthCallback:
    async def test_success_stores_refresh_token(
        self, client: AsyncClient, session: AsyncSession, uploaded_user: dict
    ) -> None:
        http = pin_http_clients()
        http.gphotos_oauth.get_access_token.return_value = OAuth2Token(
            {"refresh_token": "rt-new-123", "access_token": "at-xyz"}
        )

        resp = await oauth_callback(client)

        assert resp.status_code == 303
        assert "?error" not in resp.headers["location"]

        user = await session.get(User, uploaded_user["id"])
        assert user is not None
        assert user.google_photos_refresh_token is not None
        assert user.google_photos_connected_at is not None

    @pytest.mark.usefixtures("uploaded_user")
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
        http = pin_http_clients()
        if side_effect is None:
            http.gphotos_oauth.get_access_token.return_value = token
        else:
            http.gphotos_oauth.get_access_token.side_effect = side_effect

        resp = await oauth_callback(client)

        assert_error_redirect(resp)

    @pytest.mark.usefixtures("uploaded_user")
    async def test_state_csrf_mismatch_redirects_with_error(
        self, client: AsyncClient
    ) -> None:
        resp = await oauth_callback(
            client, csrf="state-csrf-B", cookie_csrf="cookie-csrf-A"
        )

        assert_error_redirect(resp)

    @pytest.mark.usefixtures("uploaded_user")
    async def test_passes_pkce_verifier_to_token_exchange(
        self, client: AsyncClient
    ) -> None:
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
    async def test_expired_token_disconnects_google_photos(
        self,
        client: AsyncClient,
        session: AsyncSession,
        google_photos_routes: GooglePhotosRoutes,
    ) -> None:
        http = await connected_google_photos_http(client, session)
        http.gphotos_oauth.refresh_token.side_effect = RefreshTokenError(
            "refresh failed",
            Response(
                400,
                json={"error": "invalid_grant"},
                request=Request("POST", "https://oauth2.googleapis.com/token"),
            ),
        )

        resp = await google_photos_routes.create_session()

        assert resp.status_code == 401
        user = (await session.exec(select(User))).one()
        await session.refresh(user)
        assert user.google_photos_refresh_token is None
        assert user.google_photos_connected_at is None


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

        assert (await user_routes.current_ok())["google_photos_connected_at"] is None

        await session.refresh(user)
        assert user.google_photos_connected_at is None

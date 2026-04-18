"""Integration tests for Google Photos routes.

Tests auth gating and disconnect. The full upgrade flow requires mocking
the Google Picker API extensively, which is best tested E2E. The matching
algorithm is already covered by unit tests in test_media_upgrade.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.routes.google_photos import _validate_match_names
from app.core.config import get_settings
from app.logic.media_upgrade import MatchResult
from app.models.user import User

from .factories import (
    connect_google_photos,
    sign_in_and_upload,
)

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


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

        resp = await client.delete("/api/v1/google-photos/connection")
        assert resp.status_code == 204

        # Verify tokens cleared in DB
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

        mock_token_resp = SimpleNamespace(access_token="fresh-token")  # noqa: S106
        mock_picker = AsyncMock()
        mock_picker.return_value.id = "session-abc"
        mock_picker.return_value.picker_uri = "https://photos.google.com/picker/abc"

        with (
            patch(
                "app.api.v1.routes.google_photos.refresh_access_token",
                return_value=mock_token_resp,
            ),
            patch(
                "app.api.v1.routes.google_photos.create_picker_session",
                mock_picker,
            ),
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

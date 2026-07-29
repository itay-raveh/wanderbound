"""Authentication and user factories."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import jwt as jwt_module

from app.core.config import get_settings
from app.logic.upload import TripMeta
from app.models.user import PSUser, User

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

AID = "trip-1"

GOOGLE_PAYLOAD = {
    "sub": "google-123",
    "given_name": "Test",
    "picture": "https://example.com/photo.jpg",
}

MICROSOFT_PAYLOAD = {
    "sub": "microsoft-456",
    "given_name": "Test",
    "name": "Test Microsoft",
    "iss": "https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000/v2.0",
}

_DEFAULT_PAYLOADS = {"google": GOOGLE_PAYLOAD, "microsoft": MICROSOFT_PAYLOAD}

PS_USER = PSUser(
    id=999,
    first_name="Zip",
    locale="en-US",
    unit_is_km=True,
    temperature_is_celsius=True,
)

TRIPS = [TripMeta(id="trip-1", title="Test Trip", step_count=5, country_codes=["nl"])]


@contextmanager
def mock_jwt(
    provider: str = "google",
    payload: dict | None = None,
    *,
    decode_error: bool = False,
    ensure_configured: bool = True,
) -> Generator[None]:
    mock_key = MagicMock()
    mock_key.key = "fake-key"
    decode_kwargs: dict = (
        {"side_effect": jwt_module.InvalidTokenError}
        if decode_error
        else {"return_value": payload or _DEFAULT_PAYLOADS[provider]}
    )
    # Ensure the client-ID gate passes even when the env var is absent.
    settings = get_settings()
    attr = f"{provider.upper()}_CLIENT_ID"
    prev = getattr(settings, attr)
    if ensure_configured and not prev:
        setattr(settings, attr, "test")
    try:
        with (
            patch(
                f"app.api.v1.routes.auth._{provider}_jwks.get_signing_key_from_jwt",
                return_value=mock_key,
            ),
            patch("jwt.decode", **decode_kwargs),
        ):
            yield
    finally:
        setattr(settings, attr, prev)


async def sign_in(
    client: AsyncClient, provider: str = "google", payload: dict | None = None
) -> None:
    """Set a pending_signup session cookie via /auth/{provider}."""
    with mock_jwt(provider, payload=payload):
        resp = await client.post(
            f"/api/v1/auth/{provider}", json={"credential": "fake"}
        )
    assert resp.status_code == 200


async def sign_in_user(
    client: AsyncClient,
    session: AsyncSession,
    users_dir: Path,
    provider: str = "google",
    payload: dict | None = None,
) -> dict:
    claims = payload or _DEFAULT_PAYLOADS[provider]
    first_name = (
        claims.get("given_name")
        or (claims.get("name") if provider == "microsoft" else None)
        or PS_USER.first_name
        or "Anonymous"
    )
    user = make_user(
        uid=PS_USER.id,
        google_sub=claims["sub"] if provider == "google" else None,
        microsoft_sub=claims["sub"] if provider == "microsoft" else None,
        first_name=first_name,
    )
    user.profile_image_url = claims.get("picture")
    session.add(user)
    await session.commit()

    with mock_jwt(provider, payload=claims):
        resp = await client.post(
            f"/api/v1/auth/{provider}", json={"credential": "fake"}
        )
    assert resp.status_code == 200
    return resp.json()


async def sign_in_uploaded_user(
    client: AsyncClient,
    session: AsyncSession,
    *,
    provider: str = "google",
    payload: dict | None = None,
) -> dict:
    users_dir = get_settings().USERS_FOLDER
    users_dir.mkdir(parents=True, exist_ok=True)
    return await sign_in_user(client, session, users_dir, provider, payload)


# ---------------------------------------------------------------------------
# DB insert helpers
# ---------------------------------------------------------------------------

GOOGLE_REFRESH_TOKEN = "1//0fake-refresh-token-for-tests"  # noqa: S105


def make_user(
    uid: int = 1,
    *,
    album_ids: list[str] | None = None,
    google_sub: str | None = None,
    microsoft_sub: str | None = None,
    first_name: str = "Test",
    locale: str = "en-US",
    unit_is_km: bool = True,
    temperature_is_celsius: bool = True,
    is_demo: bool = False,
    last_active_at: datetime | None = None,
) -> User:
    resolved_google_sub = google_sub
    if resolved_google_sub is None and microsoft_sub is None and not is_demo:
        resolved_google_sub = f"google-{uid}"
    user = User(
        id=uid,
        google_sub=resolved_google_sub,
        microsoft_sub=microsoft_sub,
        first_name=first_name,
        locale=locale,
        unit_is_km=unit_is_km,
        temperature_is_celsius=temperature_is_celsius,
        album_ids=album_ids if album_ids is not None else [AID],
        is_demo=is_demo,
        last_active_at=last_active_at or datetime.now(UTC),
    )
    user.folder.mkdir(parents=True, exist_ok=True)
    return user


async def connect_google_photos(session: AsyncSession, uid: int) -> None:
    """Mark user as Google Photos connected with a refresh token."""
    user = await session.get(User, uid)
    assert user is not None
    user.google_photos_refresh_token = GOOGLE_REFRESH_TOKEN
    user.google_photos_connected_at = datetime.now(UTC)
    session.add(user)
    await session.flush()


async def sign_in_connected_google_photos(
    client: AsyncClient,
    session: AsyncSession,
) -> int:
    user_data = await sign_in_uploaded_user(client, session, provider="google")
    uid = user_data["id"]
    await connect_google_photos(session, uid)
    return uid

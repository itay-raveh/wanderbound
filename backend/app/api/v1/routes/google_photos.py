"""Google Photos Picker API routes.

OAuth2 authorize/callback, Picker session management, and upgrade SSE.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from httpx_oauth.oauth2 import (
    GetAccessTokenError,
    RevokeTokenError,
)
from pydantic import BaseModel

from app.core.config import get_settings
from app.models.google_photos import PickerSessionId
from app.services.google_photos import (
    create_picker_session,
    delete_picker_session,
    evict_cached_media_items,
    poll_picker_session,
)

from ..deps import HttpClientsDep, SessionDep, UserDep
from .google_photos_oauth import (
    clear_oauth_cookie as _clear_oauth_cookie,
    code_challenge as _code_challenge,
    decode_oauth_cookie as _decode_oauth_cookie,
    decode_state as _decode_state,
    encode_state as _encode_state,
    issue_oauth_cookie as _issue_oauth_cookie,
)
from .google_photos_upgrade import (
    _ensure_fresh_access_token,
    _require_google_user,
    router as upgrade_router,
)

logger = structlog.get_logger(__name__)

_OAUTH_COOKIE = "gphotos_oauth"

router = APIRouter(
    prefix="/google-photos",
    tags=["google-photos"],
    dependencies=[Depends(_require_google_user)],
)

# ---------------------------------------------------------------------------
# OAuth2 authorize / callback
# ---------------------------------------------------------------------------


@router.get("/authorize")
async def authorize(
    request: Request,
    user: UserDep,
    http: HttpClientsDep,
    nonce: Annotated[str, Query(min_length=8, max_length=64)],
) -> RedirectResponse:
    frontend_url = str(get_settings().PUBLIC_URL).rstrip("/")
    redirect_uri = f"{frontend_url}{request.url_for('google_photos_callback').path}"
    # 303 See Other per RFC 9110 §15.4.4 for redirect-after-state-change.
    resp = RedirectResponse(url="", status_code=status.HTTP_303_SEE_OTHER)
    csrf, verifier = _issue_oauth_cookie(resp)
    state = _encode_state(csrf, nonce, redirect_uri)
    resp.headers["location"] = await http.gphotos_oauth.get_authorization_url(
        redirect_uri,
        state=state,
        code_challenge=_code_challenge(verifier),
        code_challenge_method="S256",
        extras_params={"access_type": "offline", "prompt": "consent"},
    )
    return resp


def _redirect_to_popup_bridge(
    nonce: str | None, *, error: bool = False
) -> RedirectResponse:
    frontend_url = str(get_settings().PUBLIC_URL).rstrip("/")
    url = f"{frontend_url}/oauth-connected.html"
    params = []
    if error:
        params.append("error")
    if nonce:
        params.append(f"nonce={nonce}")
    if params:
        url += "?" + "&".join(params)
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/callback", name="google_photos_callback")
async def callback(  # noqa: PLR0913
    request: Request,
    user: UserDep,
    http: HttpClientsDep,
    session: SessionDep,
    code: str,
    state: str,
) -> RedirectResponse:
    payload = _decode_state(state)
    cookie_data = _decode_oauth_cookie(request.cookies.get(_OAUTH_COOKIE))
    if (
        payload is None
        or cookie_data is None
        or not secrets.compare_digest(cookie_data["csrf"], payload["csrf"])
    ):
        logger.warning("google_photos.oauth_state_mismatch", user_id=user.id)
        resp = _redirect_to_popup_bridge(
            payload["nonce"] if payload else None, error=True
        )
        _clear_oauth_cookie(resp)
        return resp

    try:
        token = await http.gphotos_oauth.get_access_token(
            code, payload["redirect_uri"], code_verifier=cookie_data["verifier"]
        )
    except GetAccessTokenError as exc:
        logger.error(  # noqa: TRY400
            "google_photos.callback_failed",
            user_id=user.id,
            error_type=type(exc).__name__,
        )
        resp = _redirect_to_popup_bridge(payload["nonce"], error=True)
        _clear_oauth_cookie(resp)
        return resp

    refresh_token = token.get("refresh_token")
    if not refresh_token:
        logger.warning("google_photos.no_refresh_token", user_id=user.id)
        resp = _redirect_to_popup_bridge(payload["nonce"], error=True)
        _clear_oauth_cookie(resp)
        return resp

    user.google_photos_refresh_token = refresh_token
    user.google_photos_connected_at = datetime.now(UTC)
    session.add(user)
    await session.commit()
    logger.info("google_photos.connected", user_id=user.id)
    resp = _redirect_to_popup_bridge(payload["nonce"])
    _clear_oauth_cookie(resp)
    return resp


# ---------------------------------------------------------------------------
# Picker session management
#
# Session ownership: Google's Picker API binds each session to the OAuth
# credentials that created it. Every endpoint below resolves the *current*
# user's access token via _ensure_fresh_access_token(), so User B cannot
# interact with User A's session even if they guess the ID.
# ---------------------------------------------------------------------------


class PickerSessionResponse(BaseModel):
    session_id: PickerSessionId
    picker_uri: str


@router.post("/sessions")
async def create_session(
    user: UserDep,
    http: HttpClientsDep,
    session: SessionDep,
    max_item_count: Annotated[int | None, Query(ge=0)] = None,
) -> PickerSessionResponse:
    access_token = await _ensure_fresh_access_token(http, user, session)
    picker = await create_picker_session(
        http.gphotos_picker,
        access_token,
        max_item_count=max_item_count,
    )
    return PickerSessionResponse(
        session_id=picker.id,
        picker_uri=picker.picker_uri,
    )


class SessionStatusResponse(BaseModel):
    ready: bool


@router.get("/sessions/{session_id}")
async def poll_session(
    session_id: PickerSessionId,
    user: UserDep,
    http: HttpClientsDep,
    session: SessionDep,
) -> SessionStatusResponse:
    access_token = await _ensure_fresh_access_token(http, user, session)
    data = await poll_picker_session(http.gphotos_picker, session_id, access_token)
    return SessionStatusResponse(ready=data.media_items_set)


@router.delete("/sessions/{session_id}", status_code=204)
async def close_session(
    session_id: PickerSessionId,
    user: UserDep,
    http: HttpClientsDep,
    session: SessionDep,
) -> None:
    access_token = await _ensure_fresh_access_token(http, user, session)
    await delete_picker_session(http.gphotos_picker, session_id, access_token)
    evict_cached_media_items(user.id, [session_id])


# ---------------------------------------------------------------------------
# SSE matching + upgrade
# ---------------------------------------------------------------------------

router.include_router(upgrade_router)


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(user: UserDep, http: HttpClientsDep, session: SessionDep) -> None:
    if user.google_photos_refresh_token:
        try:
            await http.gphotos_oauth.revoke_token(user.google_photos_refresh_token)
        except (RevokeTokenError, httpx.HTTPError) as exc:
            logger.warning(
                "google_photos.token_revoke_failed",
                user_id=user.id,
                error_type=type(exc).__name__,
            )
    user.google_photos_refresh_token = None
    user.google_photos_connected_at = None
    session.add(user)
    await session.commit()

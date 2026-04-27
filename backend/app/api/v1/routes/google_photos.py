"""Google Photos Picker API routes.

OAuth2 authorize/callback, Picker session management, and upgrade SSE.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from collections.abc import AsyncIterable
from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.sse import EventSourceResponse
from httpx_oauth.oauth2 import (
    GetAccessTokenError,
    OAuth2Token,
    RefreshTokenError,
    RevokeTokenError,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.locks import try_advisory_lock
from app.logic.media_upgrade.phash_matching import MatchResult
from app.logic.media_upgrade.pipeline import (
    UpgradeEvent,
    UpgradeFailed,
    run_matching,
    run_upgrade,
)
from app.models.album import Album
from app.models.google_photos import PickedMediaItem, PickerSessionId
from app.models.step import Step
from app.services.google_photos import (
    AccessToken,
    AccessTokenGetter,
    RefreshToken,
    create_picker_session,
    delete_picker_session,
    ensure_fresh_token,
    get_media_items,
    poll_picker_session,
)

from ..deps import HttpClientsDep, SessionDep, UserDep, album_dir as _album_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OAuth transient state: signed cookie (carries csrf + PKCE verifier) +
# signed state param (carries csrf, nonce, redirect_uri). Callback validates
# both signatures and double-submits csrf across cookie/state.
#
# Pattern: NextAuth-style separate signed cookie for OAuth state + OWASP
# signed double-submit. PKCE S256 per RFC 7636.
# ---------------------------------------------------------------------------

_OAUTH_COOKIE = "gphotos_oauth"
_OAUTH_COOKIE_PATH = "/api/v1/google-photos/callback"
_STATE_TTL_S = 600


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().SECRET_KEY, salt="gphotos-oauth-state")


def _oauth_cookie_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        get_settings().SECRET_KEY, salt="gphotos-oauth-cookie"
    )


def _code_challenge(verifier: str) -> str:
    """Derive the PKCE S256 challenge from a verifier (RFC 7636)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _issue_oauth_cookie(response: Response) -> tuple[str, str]:
    """Issue the signed OAuth cookie carrying csrf + PKCE verifier.

    Verifier is 86 chars via ``secrets.token_urlsafe(64)`` - within the
    RFC 7636 [43, 128] range and using the url-safe alphabet (subset of
    the unreserved chars the RFC permits).
    """
    csrf = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    signed = _oauth_cookie_serializer().dumps({"csrf": csrf, "verifier": verifier})
    response.set_cookie(
        _OAUTH_COOKIE,
        signed,
        max_age=_STATE_TTL_S,
        httponly=True,
        secure=get_settings().ENVIRONMENT != "local",
        samesite="lax",
        path=_OAUTH_COOKIE_PATH,
    )
    return csrf, verifier


def _decode_oauth_cookie(raw: str | None) -> dict[str, str] | None:
    if raw is None:
        return None
    try:
        return _oauth_cookie_serializer().loads(raw, max_age=_STATE_TTL_S)
    except BadSignature, SignatureExpired:
        return None


def _clear_oauth_cookie(response: Response) -> None:
    response.delete_cookie(_OAUTH_COOKIE, path=_OAUTH_COOKIE_PATH)


def _encode_state(csrf: str, nonce: str, redirect_uri: str) -> str:
    return _state_serializer().dumps(
        {"csrf": csrf, "nonce": nonce, "redirect_uri": redirect_uri}
    )


def _decode_state(token: str) -> dict[str, str] | None:
    try:
        return _state_serializer().loads(token, max_age=_STATE_TTL_S)
    except BadSignature, SignatureExpired:
        return None


def _validate_match_names(matches: list[MatchResult], valid_names: set[str]) -> None:
    """Raise 422 if any match references a file not in the album."""
    for m in matches:
        if m.local_name not in valid_names:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Unknown media file: {m.local_name}",
            )


def _require_google_user(user: UserDep) -> None:
    """Raise 403 if the user is not linked to a Google account."""
    if not user.google_sub:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Google Photos upgrade requires a Google account",
        )


async def _snapshot_album(uid: int, aid: str) -> Album:
    """Read the album in a short-lived session and release the connection.

    Used before SSE streams so the DB connection is not held for the full
    duration of the stream. ``expire_on_commit=False`` keeps already-loaded
    attributes accessible after the session closes.
    """
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        return await session.get_one(Album, (uid, aid))


async def _snapshot_album_and_steps(uid: int, aid: str) -> tuple[Album, list[Step]]:
    """Read album + its steps in a short-lived session."""
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        album = await session.get_one(Album, (uid, aid))
        step_rows = (
            await session.exec(
                select(Step)
                .where(Step.uid == uid, Step.aid == aid)
                .order_by(col(Step.timestamp))
            )
        ).all()
    return album, list(step_rows)


router = APIRouter(
    prefix="/google-photos",
    tags=["google-photos"],
    dependencies=[Depends(_require_google_user)],
)


def _get_refresh_token(user: UserDep) -> RefreshToken:
    """Return the stored refresh token or raise 400 if not connected.

    ``_get_user`` has already collapsed token-lost state to "disconnected",
    so a null ``connected_at`` is the single disconnected signal and a null
    ``refresh_token`` should be impossible at this point.
    """
    if (
        user.google_photos_connected_at is None
        or user.google_photos_refresh_token is None
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Google Photos not connected. Please authorize first.",
        )
    return user.google_photos_refresh_token


def _build_token_getter(
    http: HttpClientsDep, refresh_token: RefreshToken
) -> AccessTokenGetter:
    """Return an async callable that yields a fresh access token on demand.

    A closure over a shared ``OAuth2Token`` cache lets many concurrent
    pipeline tasks reuse the same live token (and refresh it once when it
    nears expiry) without the ceremony of a dedicated class.
    """
    token: OAuth2Token | None = None

    async def get() -> AccessToken:
        nonlocal token
        token = await ensure_fresh_token(http.gphotos_oauth, refresh_token, token)
        return token["access_token"]

    return get


async def _ensure_fresh_access_token(
    http: HttpClientsDep, user: UserDep
) -> AccessToken:
    """One-shot fetch for single-request endpoints (no caching needed)."""
    refresh_token = _get_refresh_token(user)
    try:
        token = await http.gphotos_oauth.refresh_token(refresh_token)
    except RefreshTokenError as exc:
        # Avoid logger.exception: httpx request bodies would leak the
        # plaintext refresh token and client secret into Sentry.
        logger.error(  # noqa: TRY400
            "Failed to refresh Google Photos access token for user %d: %s",
            user.id,
            type(exc).__name__,
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Google Photos authorization expired. Please reconnect.",
        ) from None
    return token["access_token"]


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
    redirect_uri = str(request.url_for("google_photos_callback"))
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
    frontend_url = str(get_settings().VITE_FRONTEND_URL).rstrip("/")
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
        logger.warning("OAuth state/CSRF mismatch for user %d", user.id)
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
            "Google Photos OAuth callback failed for user %d: %s: %s",
            user.id,
            type(exc).__name__,
            exc,
        )
        resp = _redirect_to_popup_bridge(payload["nonce"], error=True)
        _clear_oauth_cookie(resp)
        return resp

    refresh_token = token.get("refresh_token")
    if not refresh_token:
        logger.warning("No refresh token for user %d", user.id)
        resp = _redirect_to_popup_bridge(payload["nonce"], error=True)
        _clear_oauth_cookie(resp)
        return resp

    user.google_photos_refresh_token = refresh_token
    user.google_photos_connected_at = datetime.now(UTC)
    session.add(user)
    await session.commit()
    logger.info("OAuth callback complete: user %d connected", user.id)
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
async def create_session(user: UserDep, http: HttpClientsDep) -> PickerSessionResponse:
    access_token = await _ensure_fresh_access_token(http, user)
    picker = await create_picker_session(http.gphotos_picker, access_token)
    return PickerSessionResponse(
        session_id=picker.id,
        picker_uri=picker.picker_uri,
    )


class SessionStatusResponse(BaseModel):
    ready: bool


@router.get("/sessions/{session_id}")
async def poll_session(
    session_id: PickerSessionId, user: UserDep, http: HttpClientsDep
) -> SessionStatusResponse:
    access_token = await _ensure_fresh_access_token(http, user)
    data = await poll_picker_session(http.gphotos_picker, session_id, access_token)
    return SessionStatusResponse(ready=data.media_items_set)


@router.delete("/sessions/{session_id}", status_code=204)
async def close_session(
    session_id: PickerSessionId, user: UserDep, http: HttpClientsDep
) -> None:
    access_token = await _ensure_fresh_access_token(http, user)
    await delete_picker_session(http.gphotos_picker, session_id, access_token)


# ---------------------------------------------------------------------------
# SSE matching + upgrade
# ---------------------------------------------------------------------------


@router.get(
    "/match/{aid}",
    response_class=EventSourceResponse,
    responses={200: {"model": list[UpgradeEvent]}},
)
async def match_media(
    aid: str,
    user: UserDep,
    http: HttpClientsDep,
    session_id: Annotated[PickerSessionId, Query()],
) -> AsyncIterable[UpgradeEvent]:
    # Validate before streaming - HTTPExceptions need uncommitted headers.
    async with try_advisory_lock(f"gphotos-match:{user.id}:{aid}") as acquired:
        if not acquired:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A matching run is already in progress for this album.",
            )
        tokens = _build_token_getter(http, _get_refresh_token(user))
        access_token = await tokens()

        album, step_rows = await _snapshot_album_and_steps(user.id, aid)

        album_dir = _album_dir(user, aid)
        already_upgraded = dict(album.upgraded_media)
        step_timestamps = [s.timestamp for s in step_rows]
        step_ids = [s.id for s in step_rows]
        media_by_step = {
            s.id: [name for page in s.pages for name in page] + s.unused
            for s in step_rows
        }

        items = await get_media_items(http.gphotos_picker, session_id, access_token)

        try:
            async for event in run_matching(
                http,
                album_dir=album_dir,
                media_by_step=media_by_step,
                step_timestamps=step_timestamps,
                step_ids=step_ids,
                google_items=items,
                tokens=tokens,
                already_upgraded=already_upgraded,
            ):
                yield event
        except Exception as exc:  # noqa: BLE001
            # logger.exception would capture the full traceback; a token-refresh
            # request body contains the plaintext refresh token and client
            # secret (see _ensure_fresh_access_token for context).
            logger.error(  # noqa: TRY400
                "Matching failed for album %s: %s: %s", aid, type(exc).__name__, exc
            )
            yield UpgradeFailed(detail="Matching failed unexpectedly.")


class UpgradeRequest(BaseModel):
    session_ids: list[PickerSessionId] = Field(max_length=100)
    matches: list[MatchResult] = Field(max_length=10_000)


@router.post(
    "/upgrade/{aid}",
    response_class=EventSourceResponse,
    responses={200: {"model": list[UpgradeEvent]}},
)
async def upgrade_media(
    aid: str,
    body: UpgradeRequest,
    user: UserDep,
    http: HttpClientsDep,
) -> AsyncIterable[UpgradeEvent]:
    # Validate before streaming - HTTPExceptions need uncommitted headers.
    if user.google_photos_connected_at is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Google Photos not connected. Please authorize first.",
        )

    async with try_advisory_lock(f"gphotos-upgrade:{user.id}:{aid}") as acquired:
        if not acquired:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "An upgrade is already running for this album.",
            )

        album = await _snapshot_album(user.id, aid)
        valid_names = {m.name for m in album.media}
        already_upgraded = dict(album.upgraded_media)

        _validate_match_names(body.matches, valid_names)

        tokens = _build_token_getter(http, _get_refresh_token(user))
        access_token = await tokens()

        all_items: list[PickedMediaItem] = []
        for sid in body.session_ids:
            all_items.extend(
                await get_media_items(http.gphotos_picker, sid, access_token)
            )
        items_by_id = {item.id: item for item in all_items}

        async for event in run_upgrade(
            clients=http,
            uid=user.id,
            aid=aid,
            album_dir=_album_dir(user, aid),
            matches=body.matches,
            google_items_by_id=items_by_id,
            already_upgraded=already_upgraded,
            tokens=tokens,
            session_ids=body.session_ids,
        ):
            yield event


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(user: UserDep, http: HttpClientsDep, session: SessionDep) -> None:
    if user.google_photos_refresh_token:
        try:
            await http.gphotos_oauth.revoke_token(user.google_photos_refresh_token)
        except (RevokeTokenError, httpx.HTTPError) as exc:
            logger.warning("Token revoke failed: %s", type(exc).__name__)
    user.google_photos_refresh_token = None
    user.google_photos_connected_at = None
    session.add(user)
    await session.commit()

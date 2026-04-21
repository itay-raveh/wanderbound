"""Google Photos Picker API routes.

OAuth2 authorize/callback, Picker session management, and upgrade SSE.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterable
from datetime import UTC, datetime
from typing import Annotated

import httpx
from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel, Field
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.locks import try_advisory_lock
from app.logic.media_upgrade.phash_matching import MatchResult
from app.logic.media_upgrade.pipeline import (
    UpgradeError,
    UpgradeEvent,
    run_matching,
    run_upgrade,
)
from app.models.album import Album
from app.models.step import Step
from app.services.google_photos import (
    AccessToken,
    PickedMediaItem,
    PickerSessionId,
    RefreshToken,
    TokenProvider,
    create_picker_session,
    delete_picker_session,
    get_media_items,
    get_oauth,
    poll_picker_session,
    refresh_access_token,
    revoke_refresh_token,
)

from ..deps import HttpClientsDep, SessionDep, UserDep, album_dir as _album_dir

logger = logging.getLogger(__name__)


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
    """Return the stored refresh token, raising HTTP errors on failure.

    `connected_at` is the source of truth for whether the user connected;
    a null `refresh_token` alongside a non-null `connected_at` means the
    stored ciphertext could not be decrypted (e.g. after SECRET_KEY rotation).
    """
    if user.google_photos_connected_at is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Google Photos not connected. Please authorize first.",
        )
    if user.google_photos_refresh_token is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Google Photos connection lost. Please reconnect.",
        )
    return user.google_photos_refresh_token


async def _get_access_token(http: HttpClientsDep, user: UserDep) -> AccessToken:
    """Exchange the stored refresh token for a fresh access token."""
    refresh_token = _get_refresh_token(user)
    try:
        token_data = await refresh_access_token(http.gphotos_token, refresh_token)
    except httpx.HTTPError as exc:
        # Log without the full traceback: httpx request bodies contain the
        # plaintext refresh token and client secret, which logger.exception
        # would capture and send to Sentry.
        logger.error(  # noqa: TRY400
            "Failed to refresh Google Photos access token for user %d: %s",
            user.id,
            type(exc).__name__,
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Google Photos authorization expired. Please reconnect.",
        ) from None
    return token_data.access_token


# ---------------------------------------------------------------------------
# OAuth2 authorize / callback
# ---------------------------------------------------------------------------


@router.get("/authorize")
async def authorize(
    request: Request,
    user: UserDep,
    nonce: Annotated[str, Query(min_length=8, max_length=64)],
) -> RedirectResponse:
    oauth = get_oauth()
    redirect_uri = str(request.url_for("google_photos_callback"))
    rv = await oauth.google_photos.create_authorization_url(
        redirect_uri, access_type="offline", prompt="consent"
    )
    await oauth.google_photos.save_authorize_data(
        request, redirect_uri=redirect_uri, **rv
    )
    request.session["oauth_nonce"] = nonce
    return RedirectResponse(rv["url"])


def _oauth_redirect(nonce: str | None, *, error: bool = False) -> RedirectResponse:
    url = f"{get_settings().VITE_FRONTEND_URL}/oauth-connected.html"
    params = []
    if error:
        params.append("error")
    if nonce:
        params.append(f"nonce={nonce}")
    if params:
        url += "?" + "&".join(params)
    return RedirectResponse(url)


@router.get("/callback", name="google_photos_callback")
async def callback(
    request: Request, user: UserDep, session: SessionDep
) -> RedirectResponse:
    nonce = request.session.pop("oauth_nonce", None)
    oauth = get_oauth()
    try:
        token = await oauth.google_photos.authorize_access_token(request)
    except OAuthError as exc:
        logger.error(  # noqa: TRY400
            "Google Photos OAuth callback failed for user %d: %s: %s",
            user.id,
            type(exc).__name__,
            exc,
        )
        return _oauth_redirect(nonce, error=True)
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        logger.warning("No refresh token for user %d", user.id)
        return _oauth_redirect(nonce, error=True)

    user.google_photos_refresh_token = refresh_token
    user.google_photos_connected_at = datetime.now(UTC)
    session.add(user)
    await session.commit()
    logger.info("OAuth callback complete: user %d connected", user.id)
    return _oauth_redirect(nonce)


# ---------------------------------------------------------------------------
# Picker session management
#
# Session ownership: Google's Picker API binds each session to the OAuth
# credentials that created it. Every endpoint below resolves the *current*
# user's access token via _get_access_token(), so User B cannot interact
# with User A's session even if they guess the ID.
# ---------------------------------------------------------------------------


class PickerSessionResponse(BaseModel):
    session_id: PickerSessionId
    picker_uri: str


@router.post("/sessions")
async def create_session(user: UserDep, http: HttpClientsDep) -> PickerSessionResponse:
    access_token = await _get_access_token(http, user)
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
    access_token = await _get_access_token(http, user)
    data = await poll_picker_session(http.gphotos_picker, session_id, access_token)
    return SessionStatusResponse(ready=data.media_items_set)


@router.delete("/sessions/{session_id}", status_code=204)
async def close_session(
    session_id: PickerSessionId, user: UserDep, http: HttpClientsDep
) -> None:
    access_token = await _get_access_token(http, user)
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
        tokens = TokenProvider(http.gphotos_token, _get_refresh_token(user))
        access_token = await tokens.get()

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
            # logger.exception would capture the full traceback; if TokenProvider
            # raised httpx.HTTPStatusError the request body contains the plaintext
            # refresh token and client secret (see _get_access_token for context).
            logger.error(  # noqa: TRY400
                "Matching failed for album %s: %s: %s", aid, type(exc).__name__, exc
            )
            yield UpgradeError(detail="Matching failed unexpectedly.")


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

        tokens = TokenProvider(http.gphotos_token, _get_refresh_token(user))
        access_token = await tokens.get()

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
        await revoke_refresh_token(http.gphotos_token, user.google_photos_refresh_token)
    user.google_photos_refresh_token = None
    user.google_photos_connected_at = None
    session.add(user)
    await session.commit()

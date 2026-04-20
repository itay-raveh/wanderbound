"""Google Photos Picker API routes.

OAuth2 authorize/callback, Picker session management, and upgrade SSE.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterable
from datetime import UTC, datetime
from pathlib import Path
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
from app.core.encryption import encrypt_token, try_decrypt_token
from app.core.locks import try_advisory_lock
from app.logic.media_upgrade import (
    MatchResult,
    UpgradeError,
    UpgradeEvent,
    apply_upgrade_results,
    execute_upgrade,
    run_matching,
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

from ..deps import SessionDep, UserDep, album_dir as _album_dir

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


router = APIRouter(
    prefix="/google-photos",
    tags=["google-photos"],
    dependencies=[Depends(_require_google_user)],
)


def _decrypt_refresh_token(user: UserDep) -> RefreshToken:
    """Decrypt the stored refresh token, raising HTTP errors on failure."""
    if not user.google_photos_refresh_token:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Google Photos not connected. Please authorize first.",
        )
    refresh_token = try_decrypt_token(user.google_photos_refresh_token)
    if not refresh_token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Google Photos connection lost. Please reconnect.",
        )
    return refresh_token


async def _get_access_token(user: UserDep) -> AccessToken:
    """Decrypt the stored refresh token and exchange it for a fresh access token."""
    refresh_token = _decrypt_refresh_token(user)
    try:
        token_data = await refresh_access_token(refresh_token)
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
async def authorize(request: Request, user: UserDep) -> dict[str, str]:
    oauth = get_oauth()
    redirect_uri = str(request.url_for("google_photos_callback"))
    rv = await oauth.google_photos.create_authorization_url(
        redirect_uri, access_type="offline", prompt="consent"
    )
    await oauth.google_photos.save_authorize_data(
        request, redirect_uri=redirect_uri, **rv
    )
    return {"authorization_url": rv["url"]}


def _oauth_redirect(*, error: bool = False) -> RedirectResponse:
    url = f"{get_settings().VITE_FRONTEND_URL}/oauth-connected.html"
    if error:
        url += "?error"
    return RedirectResponse(url)


@router.get("/callback", name="google_photos_callback")
async def callback(
    request: Request, user: UserDep, session: SessionDep
) -> RedirectResponse:
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
        return _oauth_redirect(error=True)
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        logger.warning("No refresh token for user %d", user.id)
        return _oauth_redirect(error=True)

    user.google_photos_refresh_token = encrypt_token(refresh_token)
    user.google_photos_connected_at = datetime.now(UTC)
    session.add(user)
    await session.commit()
    logger.info("OAuth callback complete: user %d connected", user.id)
    return _oauth_redirect()


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
async def create_session(user: UserDep) -> PickerSessionResponse:
    access_token = await _get_access_token(user)
    picker = await create_picker_session(access_token)
    return PickerSessionResponse(
        session_id=picker.id,
        picker_uri=picker.picker_uri,
    )


class SessionStatusResponse(BaseModel):
    ready: bool


@router.get("/sessions/{session_id}")
async def poll_session(
    session_id: PickerSessionId, user: UserDep
) -> SessionStatusResponse:
    access_token = await _get_access_token(user)
    data = await poll_picker_session(session_id, access_token)
    return SessionStatusResponse(ready=data.media_items_set)


@router.delete("/sessions/{session_id}", status_code=204)
async def close_session(session_id: PickerSessionId, user: UserDep) -> None:
    access_token = await _get_access_token(user)
    await delete_picker_session(session_id, access_token)


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
    session_id: Annotated[PickerSessionId, Query()],
) -> AsyncIterable[UpgradeEvent]:
    # Validate before streaming - HTTPExceptions need uncommitted headers.
    async with try_advisory_lock(f"gphotos-match:{user.id}:{aid}") as acquired:
        if not acquired:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A matching run is already in progress for this album.",
            )
        tokens = TokenProvider(_decrypt_refresh_token(user))
        access_token = await tokens.get()

        # Short-lived DB session: read album + steps, then release the
        # connection before the long-running matching generator starts.
        async with AsyncSession(get_engine(), expire_on_commit=False) as session:
            album = await session.get_one(Album, (user.id, aid))
            step_rows = (
                await session.exec(
                    select(Step)
                    .where(Step.uid == user.id, Step.aid == aid)
                    .order_by(col(Step.timestamp))
                )
            ).all()

        album_dir = _album_dir(user, aid)
        already_upgraded = dict(album.upgraded_media)
        step_timestamps = [s.timestamp for s in step_rows]
        step_ids = [s.id for s in step_rows]
        media_by_step = {
            s.id: [name for page in s.pages for name in page] + s.unused
            for s in step_rows
        }

        items = await get_media_items(session_id, access_token)

        try:
            async for event in run_matching(
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


async def _prepare_upgrade(
    user: UserDep,
    body: UpgradeRequest,
    session: SessionDep,
    aid: str,
) -> tuple[Album, Path, dict[str, PickedMediaItem], TokenProvider]:
    """Validate and prepare all data for the upgrade stream."""
    tokens = TokenProvider(_decrypt_refresh_token(user))
    access_token = await tokens.get()

    album = await session.get_one(Album, (user.id, aid))
    album_dir = _album_dir(user, aid)

    _validate_match_names(body.matches, {m.name for m in album.media})

    all_items: list[PickedMediaItem] = []
    for sid in body.session_ids:
        all_items.extend(await get_media_items(sid, access_token))
    items_by_id = {item.id: item for item in all_items}
    return album, album_dir, items_by_id, tokens


async def _persist_upgrade(
    uid: int,
    aid: str,
    album_dir: Path,
    matches: list[MatchResult],
    succeeded: set[str],
) -> None:
    """Write upgrade results to DB, retrying once on transient failure.

    Called from the ``finally`` block of the upgrade SSE stream, so it
    cannot yield events back to the client. On total failure the
    filesystem may be ahead of the DB; the ERROR log is the only signal.
    A future reconciliation job could fix this, but in practice transient
    DB failures rarely survive a retry.
    """
    replaced = len(succeeded)
    for attempt in range(2):
        try:
            engine = get_engine()
            async with AsyncSession(engine, expire_on_commit=False) as persist_session:
                album = await persist_session.get_one(Album, (uid, aid))
                album.media, album.upgraded_media = await apply_upgrade_results(
                    album_dir,
                    matches,
                    album.media,
                    album.upgraded_media,
                    succeeded,
                )
                persist_session.add(album)
                await persist_session.commit()
        except Exception:
            if attempt == 0:
                logger.warning(
                    "Persist attempt 1 failed, retrying after 0.5s",
                    exc_info=True,
                    extra={"uid": uid, "aid": aid, "replaced": replaced},
                )
                await asyncio.sleep(0.5)
            else:
                logger.exception(
                    "Failed to persist upgrade results - filesystem may be ahead of DB",
                    extra={"uid": uid, "aid": aid, "replaced": replaced},
                )
        else:
            logger.info(
                "Persisted upgrade results",
                extra={"uid": uid, "aid": aid, "replaced": replaced},
            )
            return


async def _cleanup_picker_sessions(
    session_ids: list[PickerSessionId],
    tokens: TokenProvider,
) -> None:
    """Best-effort cleanup of picker sessions after upgrade."""
    try:
        access_token = await tokens.get()
    except httpx.HTTPError, RuntimeError:
        logger.warning("Skipping picker session cleanup - token unavailable")
        return
    for sid in session_ids:
        try:
            await delete_picker_session(sid, access_token)
        except httpx.HTTPError:
            logger.warning("Failed to delete picker session %s", sid)


@router.post(
    "/upgrade/{aid}",
    response_class=EventSourceResponse,
    responses={200: {"model": list[UpgradeEvent]}},
)
async def upgrade_media(
    aid: str,
    body: UpgradeRequest,
    user: UserDep,
    session: SessionDep,
) -> AsyncIterable[UpgradeEvent]:
    # Validate before streaming - HTTPExceptions need uncommitted headers.
    # Quick check before acquiring the upgrade lock; full validation
    # (including decrypt) happens in _prepare_upgrade.
    if not user.google_photos_refresh_token:
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
        album, album_dir, items_by_id, tokens = await _prepare_upgrade(
            user, body, session, aid
        )

        succeeded: set[str] = set()
        try:
            async for event in execute_upgrade(
                album_dir=album_dir,
                matches=body.matches,
                google_items_by_id=items_by_id,
                tokens=tokens,
                already_upgraded=album.upgraded_media,
                succeeded=succeeded,
            ):
                yield event
        except Exception as exc:  # noqa: BLE001
            logger.error(  # noqa: TRY400
                "Upgrade failed for album %s: %s: %s", aid, type(exc).__name__, exc
            )
            yield UpgradeError(detail="Upgrade failed unexpectedly.")
        finally:
            await _persist_upgrade(user.id, aid, album_dir, body.matches, succeeded)
            await _cleanup_picker_sessions(body.session_ids, tokens)


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(user: UserDep, session: SessionDep) -> None:
    if user.google_photos_refresh_token:
        token = try_decrypt_token(user.google_photos_refresh_token)
        if token:
            await revoke_refresh_token(token)
    user.google_photos_refresh_token = None
    user.google_photos_connected_at = None
    session.add(user)
    await session.commit()

"""Google Photos Picker API routes.

OAuth2 authorize/callback, Picker session management, and upgrade SSE.
"""

from __future__ import annotations

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
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.encryption import decrypt_token, encrypt_token
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
    TokenProvider,
    create_picker_session,
    delete_picker_session,
    get_media_items,
    get_oauth,
    poll_picker_session,
    refresh_access_token,
)

from ..deps import SessionDep, UserDep

logger = logging.getLogger(__name__)

# Tracks albums currently being upgraded. The check-and-add is done without
# intervening awaits so two concurrent requests can't both pass the check.
# NOTE: process-local - does not protect across multiple workers/containers.
# Use a DB advisory lock if running multiple workers in production.
_upgrades_in_progress: set[tuple[int, str]] = set()


def _album_dir(user: UserDep, aid: str) -> Path:
    """Resolve the album directory, rejecting path traversal in ``aid``."""
    resolved = (user.trips_folder / aid).resolve()
    if not resolved.is_relative_to(user.trips_folder):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return resolved


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


async def _get_access_token(user: UserDep) -> AccessToken:
    """Decrypt the stored refresh token and exchange it for a fresh access token."""
    if not user.google_photos_refresh_token:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Google Photos not connected. Please authorize first.",
        )
    refresh_token = decrypt_token(user.google_photos_refresh_token)
    try:
        token_data = await refresh_access_token(refresh_token)
    except httpx.HTTPError:
        logger.exception(
            "Failed to refresh Google Photos access token for user %d", user.id
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
    except OAuthError:
        logger.exception("Google Photos OAuth callback failed for user %d", user.id)
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


@router.post(
    "/match/{aid}",
    response_class=EventSourceResponse,
    responses={200: {"model": list[UpgradeEvent]}},
)
async def match_media(
    aid: str,
    user: UserDep,
    session: SessionDep,
    session_id: Annotated[PickerSessionId, Query()],
) -> AsyncIterable[UpgradeEvent]:
    # Validate before streaming - HTTPExceptions need uncommitted headers.
    encrypted_refresh = user.google_photos_refresh_token
    if not encrypted_refresh:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Google Photos not connected. Please authorize first.",
        )
    tokens = TokenProvider(decrypt_token(encrypted_refresh))
    access_token = await tokens.get()

    album = await session.get_one(Album, (user.id, aid))
    album_dir = _album_dir(user, aid)

    items = await get_media_items(session_id, access_token)

    step_rows = (
        await session.exec(
            select(Step)
            .where(Step.uid == user.id, Step.aid == aid)
            .order_by(col(Step.timestamp))
        )
    ).all()
    step_timestamps = [s.timestamp for s in step_rows]
    step_ids = [s.id for s in step_rows]
    media_by_step = {
        s.id: [name for page in s.pages for name in page] + s.unused for s in step_rows
    }

    try:
        async for event in run_matching(
            album_dir=album_dir,
            media_by_step=media_by_step,
            step_timestamps=step_timestamps,
            step_ids=step_ids,
            google_items=items,
            tokens=tokens,
            already_upgraded=album.upgraded_media,
        ):
            yield event
    except Exception:
        logger.exception("Matching failed for album %s", aid)
        yield UpgradeError(detail="Matching failed unexpectedly.")


class UpgradeRequest(BaseModel):
    session_id: PickerSessionId
    matches: list[MatchResult]


async def _prepare_upgrade(
    user: UserDep,
    body: UpgradeRequest,
    session: SessionDep,
    aid: str,
    key: tuple[int, str],
) -> tuple[Album, Path, dict[str, PickedMediaItem], TokenProvider]:
    """Validate and prepare all data for the upgrade stream.

    Releases the upgrade lock on failure so a retry can proceed.
    """
    encrypted_refresh = user.google_photos_refresh_token
    if not encrypted_refresh:
        _upgrades_in_progress.discard(key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not connected")
    try:
        refresh_token = decrypt_token(encrypted_refresh)
        tokens = TokenProvider(refresh_token)
        access_token = await tokens.get()

        album = await session.get_one(Album, (user.id, aid))
        album_dir = _album_dir(user, aid)

        _validate_match_names(body.matches, {m.name for m in album.media})

        items = await get_media_items(body.session_id, access_token)
        items_by_id = {item.id: item for item in items}
    except Exception:
        _upgrades_in_progress.discard(key)
        raise
    return album, album_dir, items_by_id, tokens


async def _persist_upgrade(
    uid: int,
    aid: str,
    album_dir: Path,
    matches: list[MatchResult],
    succeeded: set[str],
) -> None:
    """Write upgrade results to DB, retrying once on transient failure."""
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
                    "Persist attempt 1 failed for album %s, retrying",
                    aid,
                    exc_info=True,
                )
            else:
                logger.exception(
                    "Failed to persist upgrade results for album %s"
                    " - filesystem may be ahead of DB",
                    aid,
                )
        else:
            return


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
    if not user.google_photos_refresh_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not connected")

    key = (user.id, aid)
    if key in _upgrades_in_progress:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An upgrade is already running for this album.",
        )
    # Register the lock immediately (no await between check and add)
    # to prevent concurrent requests from both passing the check.
    _upgrades_in_progress.add(key)

    album, album_dir, items_by_id, tokens = await _prepare_upgrade(
        user, body, session, aid, key
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
    except Exception:
        logger.exception("Upgrade failed for album %s", aid)
        yield UpgradeError(detail="Upgrade failed unexpectedly.")
    finally:
        await _persist_upgrade(user.id, aid, album_dir, body.matches, succeeded)
        try:
            await delete_picker_session(body.session_id, await tokens.get())
        except httpx.HTTPError, RuntimeError:
            logger.warning("Failed to delete picker session %s", body.session_id)
        finally:
            _upgrades_in_progress.discard(key)


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(user: UserDep, session: SessionDep) -> None:
    user.google_photos_refresh_token = None
    user.google_photos_connected_at = None
    session.add(user)
    await session.commit()

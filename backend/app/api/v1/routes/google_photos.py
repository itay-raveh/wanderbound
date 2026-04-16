"""Google Photos Picker API routes.

OAuth2 authorize/callback, Picker session management, and upgrade SSE.
"""

import asyncio
import logging
from collections.abc import AsyncIterable
from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel
from sqlmodel import select

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
    PickerSessionId,
    create_picker_session,
    delete_picker_session,
    get_media_items,
    get_oauth,
    poll_picker_session,
    refresh_access_token,
)

from ..deps import SessionDep, UserDep

logger = logging.getLogger(__name__)

# Per-album lock prevents concurrent upgrades to the same album from
# racing on temp files, disk renames, and DB commits.
_album_locks: dict[tuple[int, str], asyncio.Lock] = {}


def _get_album_lock(uid: int, aid: str) -> asyncio.Lock:
    key = (uid, aid)
    if key not in _album_locks:
        _album_locks[key] = asyncio.Lock()
    return _album_locks[key]


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
    url = await oauth.google_photos.create_authorization_url(
        redirect_uri, access_type="offline", prompt="consent"
    )
    request.session["google_photos_state"] = url["state"]
    return {"authorization_url": url["url"]}


@router.get("/callback", name="google_photos_callback")
async def callback(
    request: Request, user: UserDep, session: SessionDep
) -> dict[str, str]:
    oauth = get_oauth()
    redirect_uri = str(request.url_for("google_photos_callback"))
    token = await oauth.google_photos.authorize_access_token(
        request, redirect_uri=redirect_uri
    )
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No refresh token received. Try disconnecting and reconnecting.",
        )

    user.google_photos_refresh_token = encrypt_token(refresh_token)
    user.google_photos_connected_at = datetime.now(UTC)
    session.add(user)
    await session.commit()
    return {"status": "connected"}


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
    access_token = await _get_access_token(user)

    album = await session.get_one(Album, (user.id, aid))
    album_dir = user.trips_folder / aid

    items = await get_media_items(session_id, access_token)
    media_names = [m.name for m in album.media]

    step_rows = (
        await session.exec(
            select(Step)
            .where(Step.uid == user.id, Step.aid == aid)
            .order_by(Step.timestamp)  # type: ignore[union-attr]
        )
    ).all()
    step_timestamps = [s.timestamp for s in step_rows]
    step_ids = [s.id for s in step_rows]

    try:
        async for event in run_matching(
            album_dir=album_dir,
            media_names=media_names,
            step_timestamps=step_timestamps,
            step_ids=step_ids,
            google_items=items,
            access_token=access_token,
        ):
            yield event
    except Exception:
        logger.exception("Matching failed for album %s", aid)
        yield UpgradeError(detail="Matching failed unexpectedly.")


class UpgradeRequest(BaseModel):
    session_id: PickerSessionId
    matches: list[MatchResult]


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
    lock = _get_album_lock(user.id, aid)
    if lock.locked():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An upgrade is already running for this album.",
        )

    async with lock:
        access_token = await _get_access_token(user)

        album = await session.get_one(Album, (user.id, aid))
        album_dir = user.trips_folder / aid

        # Validate every match references an actual album file (prevents path traversal)
        valid_names = {m.name for m in album.media}
        for m in body.matches:
            if m.local_name not in valid_names:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"Unknown media file: {m.local_name}",
                )

        items = await get_media_items(body.session_id, access_token)
        items_by_id = {item.id: item for item in items}

        succeeded: set[str] = set()
        try:
            async for event in execute_upgrade(
                album_dir=album_dir,
                matches=body.matches,
                google_items_by_id=items_by_id,
                access_token=access_token,
                already_upgraded=album.upgraded_media,
                succeeded=succeeded,
            ):
                yield event
        except Exception:
            logger.exception("Upgrade failed for album %s", aid)
            yield UpgradeError(detail="Upgrade failed unexpectedly.")
        finally:
            # Persist results even if the client disconnects mid-stream.
            # Files already replaced on disk must be reflected in the DB.
            album.media, album.upgraded_media = await apply_upgrade_results(
                album_dir, body.matches, album.media, album.upgraded_media, succeeded
            )
            session.add(album)
            await session.commit()
            await delete_picker_session(body.session_id, access_token)
            _album_locks.pop((user.id, aid), None)


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


@router.delete("/connection")
async def disconnect(user: UserDep, session: SessionDep) -> None:
    user.google_photos_refresh_token = None
    user.google_photos_connected_at = None
    session.add(user)
    await session.commit()

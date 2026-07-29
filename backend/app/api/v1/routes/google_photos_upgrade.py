"""Google Photos matching and upgrade routes."""

from __future__ import annotations

from collections.abc import AsyncIterable
from contextlib import suppress
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.sse import EventSourceResponse
from httpx_oauth.oauth2 import (
    OAuth2Token,
    RefreshTokenError,
)
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.core.locks import try_advisory_lock
from app.core.observability import start_span
from app.logic.layout.media import is_video
from app.logic.media_upgrade.phash_matching import MatchResult
from app.logic.media_upgrade.pipeline import (
    UpgradeEvent,
    UpgradeFailed,
    run_matching,
    run_upgrade,
)
from app.logic.step_media import read_steps_with_media
from app.models.album import Album
from app.models.album_media import AlbumMedia
from app.models.google_photos import PickedMediaItem, PickerSessionId
from app.models.step import StepRead
from app.services.google_photos import (
    AccessToken,
    AccessTokenGetter,
    RefreshToken,
    ensure_fresh_token,
    evict_cached_media_items,
    get_media_items_cached,
)

from ..deps import HttpClientsDep, SessionDep, UserDep, album_dir as _album_dir

logger = structlog.get_logger(__name__)


def _picker_selection_expired(exc: Exception) -> bool:
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code == status.HTTP_404_NOT_FOUND
        and exc.request.url.host == "photospicker.googleapis.com"
        and exc.request.url.path == "/v1/mediaItems"
    )


def _http_status_code(exc: Exception) -> int | None:
    return exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None


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


async def _snapshot_upgrade_state(
    uid: int,
    aid: str,
) -> tuple[dict[str, tuple[int, int]], set[str]]:
    """Read album media dimensions and remaining upgrade candidates."""
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        await session.get_one(Album, (uid, aid))
        media_rows = (
            await session.exec(
                select(AlbumMedia).where(AlbumMedia.uid == uid, AlbumMedia.aid == aid)
            )
        ).all()
    return (
        {row.name: (row.width, row.height) for row in media_rows},
        {row.name for row in media_rows if row.upgrade_candidate},
    )


async def _snapshot_steps_and_upgrade_state(
    uid: int,
    aid: str,
) -> tuple[list[StepRead], set[str], dict[str, list[str] | None]]:
    """Read step layouts plus remaining upgrade candidates."""
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        await session.get_one(Album, (uid, aid))
        media_rows = (
            await session.exec(
                select(AlbumMedia).where(AlbumMedia.uid == uid, AlbumMedia.aid == aid)
            )
        ).all()
        step_rows = await read_steps_with_media(session, uid, aid)
    return (
        step_rows,
        {row.name for row in media_rows if row.upgrade_candidate},
        {row.name: row.perceptual_hashes for row in media_rows},
    )


router = APIRouter()


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
    http: HttpClientsDep, user: UserDep, session: SessionDep
) -> AccessToken:
    """One-shot fetch for single-request endpoints (no caching needed)."""
    refresh_token = _get_refresh_token(user)
    try:
        token = await http.gphotos_oauth.refresh_token(refresh_token)
    except RefreshTokenError as exc:
        error_code = None
        if exc.response is not None:
            with suppress(ValueError, AttributeError):
                error_code = exc.response.json().get("error")
        if error_code == "invalid_grant":
            user.google_photos_refresh_token = None
            user.google_photos_connected_at = None
            session.add(user)
            await session.commit()
            logger.warning("google_photos.authorization_invalidated", user_id=user.id)
        else:
            # Avoid logger.exception: httpx request bodies would leak the
            # plaintext refresh token and client secret into Sentry.
            logger.error(  # noqa: TRY400
                "google_photos.token_refresh_failed",
                user_id=user.id,
                error_type=type(exc).__name__,
            )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Google Photos authorization expired. Please reconnect.",
        ) from None
    return token["access_token"]


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
        try:
            tokens = _build_token_getter(http, _get_refresh_token(user))
            access_token = await tokens()

            with start_span(
                "google_photos.load_album",
                "Load album for media matching",
                **{
                    "app.workflow": "google_photos",
                    "user.id": user.id,
                    "album.id": aid,
                },
            ):
                (
                    step_rows,
                    upgrade_candidates,
                    persisted_local_hashes,
                ) = await _snapshot_steps_and_upgrade_state(user.id, aid)

            album_dir = _album_dir(user, aid)
            step_ids = [s.id for s in step_rows]
            media_by_step = {
                s.id: [name for page in s.pages for name in page.media] + s.unused
                for s in step_rows
            }

            with start_span(
                "google_photos.fetch_picked_media",
                "Fetch picked Google Photos media",
                **{
                    "app.workflow": "google_photos",
                    "user.id": user.id,
                    "album.id": aid,
                },
            ):
                items = await get_media_items_cached(
                    http.gphotos_picker,
                    uid=user.id,
                    session_id=session_id,
                    access_token=access_token,
                )

            async for event in run_matching(
                http,
                album_dir=album_dir,
                media_by_step=media_by_step,
                step_ids=step_ids,
                google_items=items,
                tokens=tokens,
                upgrade_candidates=upgrade_candidates,
                persisted_local_hashes=persisted_local_hashes,
            ):
                yield event
        except Exception as exc:  # noqa: BLE001
            # logger.exception would capture the full traceback; a token-refresh
            # request body contains the plaintext refresh token and client
            # secret (see _ensure_fresh_access_token for context).
            logger.error(  # noqa: TRY400
                "google_photos.matching.failed",
                user_id=user.id,
                album_id=aid,
                error_type=type(exc).__name__,
                status_code=_http_status_code(exc),
            )
            detail = (
                "selectionExpired"
                if _picker_selection_expired(exc)
                else "Matching failed unexpectedly."
            )
            yield UpgradeFailed(detail=detail)


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

        with start_span(
            "google_photos.load_album",
            "Load album for media upgrade",
            **{"app.workflow": "google_photos", "user.id": user.id, "album.id": aid},
        ):
            local_dimensions, upgrade_candidates = await _snapshot_upgrade_state(
                user.id,
                aid,
            )

        photo_matches = [
            match for match in body.matches if not is_video(match.local_name)
        ]
        _validate_match_names(photo_matches, set(local_dimensions))

        try:
            tokens = _build_token_getter(http, _get_refresh_token(user))
            access_token = await tokens()

            all_items: list[PickedMediaItem] = []
            with start_span(
                "google_photos.fetch_picked_media",
                "Fetch picked Google Photos media",
                **{
                    "app.workflow": "google_photos",
                    "user.id": user.id,
                    "album.id": aid,
                    "session.count": len(body.session_ids),
                },
            ):
                for sid in body.session_ids:
                    all_items.extend(
                        await get_media_items_cached(
                            http.gphotos_picker,
                            uid=user.id,
                            session_id=sid,
                            access_token=access_token,
                        )
                    )
            items_by_id = {item.id: item for item in all_items}

            try:
                async for event in run_upgrade(
                    clients=http,
                    uid=user.id,
                    aid=aid,
                    album_dir=_album_dir(user, aid),
                    matches=photo_matches,
                    google_items_by_id=items_by_id,
                    upgrade_candidates=upgrade_candidates,
                    local_dimensions=local_dimensions,
                    tokens=tokens,
                    session_ids=body.session_ids,
                ):
                    yield event
            finally:
                evict_cached_media_items(user.id, body.session_ids)
        except Exception as exc:  # noqa: BLE001
            logger.error(  # noqa: TRY400
                "google_photos.upgrade.failed",
                user_id=user.id,
                album_id=aid,
                error_type=type(exc).__name__,
                status_code=_http_status_code(exc),
            )
            detail = (
                "selectionExpired"
                if _picker_selection_expired(exc)
                else "Upgrade failed unexpectedly."
            )
            yield UpgradeFailed(detail=detail)


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------

import asyncio
import shutil
from collections.abc import AsyncIterable
from functools import cache
from pathlib import Path
from secrets import randbelow

import httpx
import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse
from httpx_oauth.oauth2 import RevokeTokenError
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.observability import start_span
from app.logic.eviction import run_eviction
from app.logic.export import (
    EXPORT_FILENAME,
    ExportEvent,
    export_user_data,
    pop_export_token,
)
from app.logic.session import cancel_session, process_stream
from app.logic.trip_processing import ProcessingEvent
from app.logic.upload import TripMeta, UploadResult, scan_user_folder
from app.models.user import (
    OAuthIdentity,
    PSUser,
    User,
    UserPublic,
    UserUpdate,
)

from ..deps import (
    HttpClientsDep,
    SessionDep,
    UserDep,
    apply_update,
    login_session,
    to_user_public,
    try_load_user,
)
from .auth import get_pending_signup

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


async def _resolve_auth(
    request: Request,
    session: SessionDep,
) -> tuple[User | None, OAuthIdentity | None]:
    """Return (existing_user, pending_signup_identity) or raise 401."""
    if existing := await try_load_user(request, session):
        return existing, None
    identity = get_pending_signup(request)
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return None, identity


def _upload_owner(existing: User | None, identity: OAuthIdentity | None) -> str:
    """Stable identifier for the auth principal behind an upload session."""
    if existing is not None:
        return f"uid:{existing.id}"
    assert identity is not None  # noqa: S101 - _resolve_auth guarantees one is set
    return f"{identity.provider}:{identity.sub}"


@cache
def _demo_fixtures() -> tuple[Path, PSUser, tuple[TripMeta, ...]]:
    """Cached - callers must not mutate the returned objects."""
    fixtures = get_settings().DEMO_FIXTURES
    ps_user, trips = scan_user_folder(fixtures)
    return fixtures, ps_user, tuple(trips)


def _demo_locale(request: Request, fallback: str) -> str:
    """Extract primary language from Accept-Language header.

    Returns the raw tag (e.g. ``en-US``); Pydantic's ``Locale`` validator
    handles normalization and rejects invalid values on model construction.
    """
    accept = request.headers.get("accept-language", "")
    if accept:
        tag = accept.split(",")[0].split(";")[0].strip()
        if 2 <= len(tag) <= 5:
            return tag
    return fallback


@router.post("/demo")
async def create_demo(
    request: Request,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> UploadResult:
    fixtures, ps_user, trips = _demo_fixtures()
    album_ids = [t.id for t in trips]

    def _link_or_copy(src: str, dst: str) -> None:
        try:
            Path(dst).hardlink_to(src)
        except OSError:
            shutil.copy2(src, dst)

    for _ in range(5):
        uid = 2_000_000_000 + randbelow(147_483_648)
        user = User(
            id=uid,
            first_name=ps_user.first_name or "Demo",
            locale=_demo_locale(request, ps_user.locale),
            unit_is_km=ps_user.unit_is_km,
            temperature_is_celsius=ps_user.temperature_is_celsius,
            living_location=ps_user.living_location,
            album_ids=album_ids,
            is_demo=True,
        )

        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            continue

        try:
            await asyncio.to_thread(
                shutil.copytree,
                fixtures,
                user.folder,
                ignore=shutil.ignore_patterns("i18n"),
                copy_function=_link_or_copy,
            )
        except OSError:
            logger.exception("demo.copy_failed", user_id=uid)
            await session.delete(user)
            await session.commit()
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None
        break
    else:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE)

    login_session(request, user.id)

    background_tasks.add_task(run_eviction, user.id)
    return UploadResult(user=await to_user_public(user, session), trips=list(trips))


async def _remove_user(
    user: User, session: SessionDep, request: Request, http: HttpClientsDep
) -> None:
    with start_span(
        "user.delete",
        "Delete user",
        **{"app.workflow": "user_delete", "user.id": user.id, "is_demo": user.is_demo},
    ):
        cancel_session(user.id)
        folder = user.folder
        if user.google_photos_refresh_token:
            try:
                await http.gphotos_oauth.revoke_token(user.google_photos_refresh_token)
            except (RevokeTokenError, httpx.HTTPError) as exc:
                logger.warning(
                    "oauth.token_revoke_failed", error_type=type(exc).__name__
                )
        await session.delete(user)
        await session.commit()
        await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)
        request.session.clear()
        logger.info("user.deleted", user_id=user.id, is_demo=user.is_demo)


@router.delete("/demo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_demo(
    user: UserDep,
    session: SessionDep,
    request: Request,
    http: HttpClientsDep,
) -> None:
    if not user.is_demo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not a demo user")
    await _remove_user(user, session, request, http)


@router.get(
    "/process",
    response_class=EventSourceResponse,
    responses={200: {"model": list[ProcessingEvent]}},
)
async def process_user(
    user: UserDep, http: HttpClientsDep, session: SessionDep
) -> AsyncIterable[ProcessingEvent]:
    async for event in process_stream(http, user, session):
        yield event


@router.get(
    "/export",
    response_class=EventSourceResponse,
    responses={200: {"model": list[ExportEvent]}},
)
async def export_data(user: UserDep, session: SessionDep) -> AsyncIterable[ExportEvent]:
    async for event in export_user_data(user, session):
        yield event


@router.get("/export/download/{token}")
async def download_export(
    token: str, background_tasks: BackgroundTasks, session: SessionDep
) -> FileResponse:
    result = await pop_export_token(session, token)
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Invalid or expired token"
        )
    background_tasks.add_task(result.unlink, missing_ok=True)
    return FileResponse(
        result,
        media_type="application/zip",
        filename=EXPORT_FILENAME,
    )


@router.get("")
async def read_user(user: UserDep, session: SessionDep) -> UserPublic:
    return await to_user_public(user, session)


@router.patch("")
async def update_user(
    update: UserUpdate, user: UserDep, session: SessionDep
) -> UserPublic:
    updated = await apply_update(session, user, update, refresh=False)
    return await to_user_public(updated, session)


@router.delete("")
async def delete_user(
    user: UserDep, session: SessionDep, request: Request, http: HttpClientsDep
) -> None:
    await _remove_user(user, session, request, http)

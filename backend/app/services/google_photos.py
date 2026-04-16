"""Google Photos Picker API service.

Handles OAuth2 (Authlib), Picker session lifecycle, media item retrieval,
and original photo byte downloads.
"""

import asyncio
import logging
import time
from functools import cache
from pathlib import Path
from typing import IO, Annotated

import httpx
from authlib.integrations.starlette_client import OAuth
from httpx_retries import Retry, RetryTransport
from pydantic import BaseModel, ConfigDict, StringConstraints
from pydantic.alias_generators import to_camel

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_PICKER_BASE = "https://photospicker.googleapis.com"
_SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"
_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
_DOWNLOAD_FLUSH_SIZE = 4 * 1024 * 1024  # 4 MB


# ---------------------------------------------------------------------------
# Semantic type aliases
# ---------------------------------------------------------------------------

type AccessToken = str
type RefreshToken = str
type PickerSessionId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._-]+$")]
type GoogleMediaId = str
type MediaFilename = str
type MimeType = str
type MediaBaseUrl = str


# ---------------------------------------------------------------------------
# OAuth2 client (Authlib)
# ---------------------------------------------------------------------------


@cache
def get_oauth() -> OAuth:
    """Return the Authlib OAuth registry for Google Photos (cached)."""
    settings = get_settings()
    oauth = OAuth()
    oauth.register(
        name="google_photos",
        server_metadata_url=_DISCOVERY_URL,
        client_id=settings.VITE_GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        client_kwargs={"scope": _SCOPE},
    )
    return oauth


# ---------------------------------------------------------------------------
# Shared HTTP clients (connection pooling + retries)
# ---------------------------------------------------------------------------

_RETRY = Retry(total=3, backoff_factor=0.5, status_forcelist={429, 500, 502, 503, 504})


@cache
def _picker_client() -> httpx.AsyncClient:
    """Shared client for Picker API calls."""
    return httpx.AsyncClient(
        transport=RetryTransport(retry=_RETRY),
        base_url=_PICKER_BASE,
        timeout=30.0,
    )


@cache
def _download_client() -> httpx.AsyncClient:
    """Shared client for photo byte downloads (longer timeout)."""
    return httpx.AsyncClient(
        transport=RetryTransport(retry=_RETRY),
        timeout=60.0,
    )


# ---------------------------------------------------------------------------
# Public domain models
# ---------------------------------------------------------------------------


class MediaFile(BaseModel):
    base_url: MediaBaseUrl
    mime_type: MimeType
    filename: MediaFilename
    width: int | None = None
    height: int | None = None


class PickedMediaItem(BaseModel):
    id: GoogleMediaId
    create_time: str
    type: str  # "PHOTO" or "VIDEO"
    media_file: MediaFile
    video_processing_status: str | None = None  # "READY", "PROCESSING", "FAILED"


class PickerSession(BaseModel):
    id: PickerSessionId
    picker_uri: str
    polling_interval: str | None = None


# ---------------------------------------------------------------------------
# Raw API response models (Pydantic-validated, internal)
#
# Google APIs return camelCase JSON. The base class handles alias generation
# so field names stay Pythonic (snake_case) while accepting camelCase input.
# ---------------------------------------------------------------------------


class _GoogleResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        alias_generator=to_camel,
        populate_by_name=True,
    )


class _MediaFileMetadata(_GoogleResponse):
    width: int | None = None
    height: int | None = None


class _VideoMetadata(_GoogleResponse):
    processing_status: str = "READY"


class _RawMediaFile(_GoogleResponse):
    base_url: str = ""
    mime_type: str = "image/jpeg"
    filename: str = ""
    media_file_metadata: _MediaFileMetadata | None = None


class _RawMediaItem(_GoogleResponse):
    id: str
    create_time: str = ""
    type: str = "PHOTO"
    media_file: _RawMediaFile = _RawMediaFile()
    video_metadata: _VideoMetadata | None = None


class _PollingConfig(_GoogleResponse):
    poll_interval: str | None = None


class _SessionResponse(_GoogleResponse):
    id: str
    picker_uri: str
    polling_config: _PollingConfig | None = None
    media_items_set: bool = False


class _MediaItemsPage(_GoogleResponse):
    media_items: list[_RawMediaItem] = []
    next_page_token: str | None = None


class _TokenResponse(_GoogleResponse):
    access_token: str


# ---------------------------------------------------------------------------
# Picker API helpers
# ---------------------------------------------------------------------------


def _picker_headers(access_token: AccessToken) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _to_media_file(raw: _RawMediaFile) -> MediaFile:
    meta = raw.media_file_metadata
    return MediaFile(
        base_url=raw.base_url,
        mime_type=raw.mime_type,
        filename=raw.filename,
        width=meta.width if meta else None,
        height=meta.height if meta else None,
    )


async def create_picker_session(access_token: AccessToken) -> PickerSession:
    """POST /v1/sessions - create a new Picker session."""
    resp = await _picker_client().post(
        "/v1/sessions",
        headers=_picker_headers(access_token),
        json={},
    )
    resp.raise_for_status()
    data = _SessionResponse.model_validate_json(resp.content)
    polling = data.polling_config
    return PickerSession(
        id=data.id,
        picker_uri=data.picker_uri,
        polling_interval=polling.poll_interval if polling else None,
    )


async def poll_picker_session(
    session_id: PickerSessionId, access_token: AccessToken
) -> _SessionResponse:
    """GET /v1/sessions/{id} - check if user is done picking."""
    resp = await _picker_client().get(
        f"/v1/sessions/{session_id}",
        headers=_picker_headers(access_token),
    )
    resp.raise_for_status()
    return _SessionResponse.model_validate_json(resp.content)


async def get_media_items(
    session_id: PickerSessionId, access_token: AccessToken
) -> list[PickedMediaItem]:
    """GET /v1/mediaItems - retrieve all selected items, handling pagination."""
    items: list[PickedMediaItem] = []
    page_token: str | None = None
    client = _picker_client()
    while True:
        params: dict[str, str] = {"sessionId": session_id}
        if page_token:
            params["pageToken"] = page_token
        resp = await client.get(
            "/v1/mediaItems",
            headers=_picker_headers(access_token),
            params=params,
        )
        resp.raise_for_status()
        page = _MediaItemsPage.model_validate_json(resp.content)
        items.extend(
            PickedMediaItem(
                id=raw.id,
                create_time=raw.create_time,
                type=raw.type,
                media_file=_to_media_file(raw.media_file),
                video_processing_status=(
                    raw.video_metadata.processing_status if raw.video_metadata else None
                ),
            )
            for raw in page.media_items
        )
        if not page.next_page_token:
            break
        page_token = page.next_page_token
    return items


async def delete_picker_session(
    session_id: PickerSessionId, access_token: AccessToken
) -> None:
    """DELETE /v1/sessions/{id} - clean up after retrieving items."""
    resp = await _picker_client().delete(
        f"/v1/sessions/{session_id}",
        headers=_picker_headers(access_token),
    )
    if resp.status_code not in (200, 204, 404):
        logger.warning(
            "Failed to delete Picker session %s: %d",
            session_id,
            resp.status_code,
        )


async def download_media_bytes(
    base_url: MediaBaseUrl, access_token: AccessToken, *, param: str = "=d"
) -> bytes:
    """Download media bytes from a baseUrl with the given parameter suffix.

    param="=d" for originals, "=w400" for thumbnails.
    """
    url = f"{base_url}{param}"
    resp = await _download_client().get(url, headers=_picker_headers(access_token))
    resp.raise_for_status()
    return resp.content


async def download_media_to_file(
    base_url: MediaBaseUrl,
    access_token: AccessToken,
    dest: Path,
    *,
    param: str = "=d",
) -> None:
    """Stream media bytes to a file on disk (avoids holding large files in RAM).

    Chunks are buffered and flushed to disk via ``asyncio.to_thread`` every
    4 MB so that synchronous ``write()`` calls don't block the event loop
    under I/O pressure.
    """
    url = f"{base_url}{param}"
    async with _download_client().stream(
        "GET", url, headers=_picker_headers(access_token)
    ) as resp:
        resp.raise_for_status()
        buf = bytearray()

        def _flush(f: IO[bytes], data: bytes) -> None:
            f.write(data)

        with dest.open("wb") as f:
            async for chunk in resp.aiter_bytes(chunk_size=256 * 1024):
                buf.extend(chunk)
                if len(buf) >= _DOWNLOAD_FLUSH_SIZE:
                    await asyncio.to_thread(_flush, f, bytes(buf))
                    buf.clear()
            if buf:
                await asyncio.to_thread(_flush, f, bytes(buf))


class TokenProvider:
    """Lazily refreshes the Google access token when it nears expiry.

    Google access tokens last 3600s. This refreshes proactively at 50min
    so long-running upgrade streams don't hit 401s mid-download.
    """

    _REFRESH_MARGIN = 3000  # refresh after 50 minutes

    def __init__(self, refresh_token: RefreshToken) -> None:
        self._refresh_token = refresh_token
        self._token: AccessToken = ""
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()
        self._revoked = False

    async def get(self) -> AccessToken:
        async with self._lock:
            if self._revoked:
                raise RuntimeError("Google refresh token has been revoked")
            now = time.monotonic()
            if self._token and now - self._fetched_at < self._REFRESH_MARGIN:
                return self._token
            try:
                data = await refresh_access_token(self._refresh_token)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (400, 401):
                    self._revoked = True
                raise
            self._token = data.access_token
            self._fetched_at = now
            return self._token


async def refresh_access_token(refresh_token: RefreshToken) -> _TokenResponse:
    """Exchange a refresh token for a fresh access token via Google's token endpoint."""
    settings = get_settings()
    resp = await _download_client().post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": settings.VITE_GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    resp.raise_for_status()
    return _TokenResponse.model_validate_json(resp.content)

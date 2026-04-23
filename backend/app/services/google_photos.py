"""Google Photos Picker API transport: OAuth2, sessions, downloads."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from httpx_oauth.clients.google import GoogleOAuth2
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

if TYPE_CHECKING:
    import httpx
    from httpx_oauth.oauth2 import OAuth2Token

from app.models.google_photos import (
    GoogleMediaBaseUrl,
    GoogleMediaFile,
    GoogleMediaType,
    PickedMediaItem,
    PickerSession,
    PickerSessionId,
    VideoProcessingStatus,
)

logger = logging.getLogger(__name__)

_PICKER_BASE = "https://photospicker.googleapis.com"
_SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"
_DOWNLOAD_FLUSH_SIZE = 4 * 1024 * 1024  # 4 MB
_MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB per file (videos)
MAX_PHOTO_BYTES = 200 * 1024 * 1024  # 200 MB per photo
_TOKEN_REFRESH_OFFSET_S = 300  # refresh 5 min before expiry


class DownloadTooLargeError(RuntimeError):
    """Raised when a download exceeds the size limit."""


def _raise_too_large(max_bytes: int) -> None:
    raise DownloadTooLargeError(
        f"Download exceeds {max_bytes // (1024 * 1024)} MB limit"
    )


type AccessToken = str
type RefreshToken = str
type AccessTokenGetter = Callable[[], Awaitable[AccessToken]]


class GooglePhotosOAuth2(GoogleOAuth2):
    """GoogleOAuth2 bound to our pre-built httpx client.

    Overriding ``get_httpx_client`` lets the OAuth flows reuse our shared
    client (cache + retries + rate-limit transports) instead of building
    a throwaway one per call.
    """

    def __init__(
        self, client_id: str, client_secret: str, http: httpx.AsyncClient
    ) -> None:
        super().__init__(client_id, client_secret, scopes=[_SCOPE])
        self._http = http

    @asynccontextmanager
    async def get_httpx_client(self) -> AsyncIterator[httpx.AsyncClient]:
        yield self._http


async def ensure_fresh_token(
    oauth: GoogleOAuth2,
    refresh_token: RefreshToken,
    token: OAuth2Token | None,
) -> OAuth2Token:
    """Return ``token`` if still fresh, else fetch a new one via refresh grant.

    ``OAuth2Token.is_expired()`` has no offset parameter in httpx-oauth 0.16,
    so we refresh proactively by comparing ``expires_at`` against
    ``time.time() + offset``. Callers hold the token locally and re-bind the
    return value each iteration.
    """
    if token is not None:
        expires_at = token.get("expires_at")
        if expires_at is None or time.time() + _TOKEN_REFRESH_OFFSET_S < expires_at:
            return token
    return await oauth.refresh_token(refresh_token)


class _GoogleResponse(BaseModel):
    # Google APIs return camelCase; snake_case fields accept it via alias.
    model_config = ConfigDict(
        extra="allow",
        alias_generator=to_camel,
        populate_by_name=True,
    )


class _MediaFileMetadata(_GoogleResponse):
    width: int | None = None
    height: int | None = None


class _VideoMetadata(_GoogleResponse):
    processing_status: VideoProcessingStatus = "READY"


class _RawMediaFile(_GoogleResponse):
    base_url: str = ""
    mime_type: str = "image/jpeg"
    filename: str = ""
    media_file_metadata: _MediaFileMetadata | None = None


class _RawMediaItem(_GoogleResponse):
    id: str
    create_time: str = ""
    type: GoogleMediaType = "PHOTO"
    media_file: _RawMediaFile = _RawMediaFile()
    video_metadata: _VideoMetadata | None = None


class _PollingConfig(_GoogleResponse):
    poll_interval: str | None = None


class _SessionResponse(_GoogleResponse):
    id: str
    picker_uri: str | None = None  # only present in create response
    polling_config: _PollingConfig | None = None
    media_items_set: bool = False


class _MediaItemsPage(_GoogleResponse):
    media_items: list[_RawMediaItem] = []
    next_page_token: str | None = None


def _picker_headers(access_token: AccessToken) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _to_media_file(raw: _RawMediaFile) -> GoogleMediaFile:
    meta = raw.media_file_metadata
    return GoogleMediaFile(
        base_url=raw.base_url,
        mime_type=raw.mime_type,
        filename=raw.filename,
        width=meta.width if meta else None,
        height=meta.height if meta else None,
    )


async def create_picker_session(
    client: httpx.AsyncClient, access_token: AccessToken
) -> PickerSession:
    resp = await client.post(
        f"{_PICKER_BASE}/v1/sessions",
        headers=_picker_headers(access_token),
        json={},
    )
    resp.raise_for_status()
    data = _SessionResponse.model_validate_json(resp.content)
    if not data.picker_uri:
        raise ValueError("Create session response missing pickerUri")
    polling = data.polling_config
    return PickerSession(
        id=data.id,
        picker_uri=data.picker_uri,
        polling_interval=polling.poll_interval if polling else None,
    )


async def poll_picker_session(
    client: httpx.AsyncClient,
    session_id: PickerSessionId,
    access_token: AccessToken,
) -> _SessionResponse:
    resp = await client.get(
        f"{_PICKER_BASE}/v1/sessions/{session_id}",
        headers=_picker_headers(access_token),
    )
    resp.raise_for_status()
    return _SessionResponse.model_validate_json(resp.content)


_MAX_MEDIA_PAGES = 100


async def get_media_items(
    client: httpx.AsyncClient,
    session_id: PickerSessionId,
    access_token: AccessToken,
) -> list[PickedMediaItem]:
    items: list[PickedMediaItem] = []
    page_token: str | None = None
    for _ in range(_MAX_MEDIA_PAGES):
        params: dict[str, str] = {"sessionId": session_id}
        if page_token:
            params["pageToken"] = page_token
        resp = await client.get(
            f"{_PICKER_BASE}/v1/mediaItems",
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
    else:
        logger.warning(
            "Hit %d-page limit for session %s (%d items fetched)",
            _MAX_MEDIA_PAGES,
            session_id,
            len(items),
        )
    return items


async def delete_picker_session(
    client: httpx.AsyncClient,
    session_id: PickerSessionId,
    access_token: AccessToken,
) -> None:
    resp = await client.delete(
        f"{_PICKER_BASE}/v1/sessions/{session_id}",
        headers=_picker_headers(access_token),
    )
    if resp.status_code not in (200, 204, 404):
        logger.warning(
            "Failed to delete Picker session %s: %d",
            session_id,
            resp.status_code,
        )


async def _stream_sized(  # noqa: PLR0913
    client: httpx.AsyncClient,
    base_url: GoogleMediaBaseUrl,
    access_token: AccessToken,
    *,
    param: str,
    max_bytes: int,
    chunk_size: int | None = None,
) -> AsyncIterator[bytes]:
    """Stream a Google Photos URL, raising ``DownloadTooLargeError`` over limit."""
    url = f"{base_url}{param}"
    async with client.stream("GET", url, headers=_picker_headers(access_token)) as resp:
        resp.raise_for_status()
        declared = resp.headers.get("content-length")
        if declared and int(declared) > max_bytes:
            _raise_too_large(max_bytes)
        total = 0
        async for chunk in resp.aiter_bytes(chunk_size=chunk_size):
            total += len(chunk)
            if total > max_bytes:
                _raise_too_large(max_bytes)
            yield chunk


async def download_media_bytes(
    client: httpx.AsyncClient,
    base_url: GoogleMediaBaseUrl,
    access_token: AccessToken,
    *,
    param: str = "=d",
    max_bytes: int = MAX_PHOTO_BYTES,
) -> bytes:
    """param="=d" for originals, "=w400" for thumbnails."""
    chunks: list[bytes] = [
        chunk
        async for chunk in _stream_sized(
            client, base_url, access_token, param=param, max_bytes=max_bytes
        )
    ]
    return b"".join(chunks)


async def download_media_to_file(  # noqa: PLR0913
    client: httpx.AsyncClient,
    base_url: GoogleMediaBaseUrl,
    access_token: AccessToken,
    dest: Path,
    *,
    param: str = "=d",
    max_bytes: int = _MAX_DOWNLOAD_BYTES,
) -> None:
    """Flushes to disk via ``asyncio.to_thread`` so ``write()`` doesn't block.

    Caller owns ``dest`` and must clean up a partial file if this raises.
    """
    buf = bytearray()
    with dest.open("wb") as f:
        async for chunk in _stream_sized(
            client,
            base_url,
            access_token,
            param=param,
            max_bytes=max_bytes,
            chunk_size=256 * 1024,
        ):
            buf.extend(chunk)
            if len(buf) >= _DOWNLOAD_FLUSH_SIZE:
                await asyncio.to_thread(f.write, bytes(buf))
                buf.clear()
        if buf:
            await asyncio.to_thread(f.write, bytes(buf))

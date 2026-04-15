"""Google Photos Picker API service.

Handles OAuth2 (Authlib), Picker session lifecycle, media item retrieval,
and original photo byte downloads.
"""

import logging
from functools import cache
from typing import Any

import httpx
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_PICKER_BASE = "https://photospicker.googleapis.com"
_SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"
_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


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
        client_secret=settings.GOOGLE_PHOTOS_CLIENT_SECRET,
        client_kwargs={"scope": _SCOPE},
    )
    return oauth


# ---------------------------------------------------------------------------
# Picker session models
# ---------------------------------------------------------------------------


class PickerSession(BaseModel):
    id: str
    picker_uri: str
    polling_interval: str | None = None


class MediaFile(BaseModel):
    base_url: str
    mime_type: str
    filename: str
    width: int | None = None
    height: int | None = None


class PickedMediaItem(BaseModel):
    id: str
    create_time: str
    type: str  # "PHOTO" or "VIDEO"
    media_file: MediaFile


# ---------------------------------------------------------------------------
# Picker API helpers
# ---------------------------------------------------------------------------


def _picker_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def create_picker_session(access_token: str) -> PickerSession:
    """POST /v1/sessions - create a new Picker session."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_PICKER_BASE}/v1/sessions",
            headers=_picker_headers(access_token),
            json={},
        )
        resp.raise_for_status()
    data = resp.json()
    polling = data.get("pollingConfig", {})
    return PickerSession(
        id=data["id"],
        picker_uri=data["pickerUri"],
        polling_interval=polling.get("pollInterval"),
    )


async def poll_picker_session(session_id: str, access_token: str) -> dict[str, Any]:
    """GET /v1/sessions/{id} - check if user is done picking."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_PICKER_BASE}/v1/sessions/{session_id}",
            headers=_picker_headers(access_token),
        )
        resp.raise_for_status()
    return resp.json()


async def get_media_items(session_id: str, access_token: str) -> list[PickedMediaItem]:
    """GET /v1/mediaItems - retrieve all selected items, handling pagination."""
    items: list[PickedMediaItem] = []
    page_token: str | None = None
    async with httpx.AsyncClient() as client:
        while True:
            params: dict[str, str] = {"sessionId": session_id}
            if page_token:
                params["pageToken"] = page_token
            resp = await client.get(
                f"{_PICKER_BASE}/v1/mediaItems",
                headers=_picker_headers(access_token),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            for raw in data.get("mediaItems", []):
                mf = raw.get("mediaFile", {})
                metadata = mf.get("mediaFileMetadata", {})
                items.append(
                    PickedMediaItem(
                        id=raw["id"],
                        create_time=raw.get("createTime", ""),
                        type=raw.get("type", "PHOTO"),
                        media_file=MediaFile(
                            base_url=mf.get("baseUrl", ""),
                            mime_type=mf.get("mimeType", "image/jpeg"),
                            filename=mf.get("filename", ""),
                            width=metadata.get("width"),
                            height=metadata.get("height"),
                        ),
                    )
                )
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    return items


async def delete_picker_session(session_id: str, access_token: str) -> None:
    """DELETE /v1/sessions/{id} - clean up after retrieving items."""
    async with httpx.AsyncClient() as client:
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


async def download_media_bytes(
    base_url: str, access_token: str, *, param: str = "=d"
) -> bytes:
    """Download media bytes from a baseUrl with the given parameter suffix.

    param="=d" for originals, "=w400" for thumbnails.
    """
    url = f"{base_url}{param}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url, headers=_picker_headers(access_token))
        resp.raise_for_status()
    return resp.content


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """Exchange a refresh token for a fresh access token via Google's token endpoint."""
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.VITE_GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_PHOTOS_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
    return resp.json()

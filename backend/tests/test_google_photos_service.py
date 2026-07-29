from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.oauth2 import OAuth2Token, RefreshTokenError

from app.services.google_photos import (
    DownloadTooLargeError,
    GoogleMediaFile,
    PickedMediaItem,
    PickerSession,
    _clear_media_items_cache,
    create_picker_session,
    download_media_to_file,
    ensure_fresh_token,
    evict_cached_media_items,
    get_media_items,
    get_media_items_cached,
)
from tests.helpers.http import async_client, json_response

_SESSION_JSON = {
    "id": "session-xyz",
    "pickerUri": "https://photos.google.com/picker/abc",
    "pollingConfig": {"pollInterval": "5s"},
    "expireTime": "2025-01-01T00:00:00Z",
    "mediaItemsSet": False,
}

_MEDIA_ITEM_JSON = {
    "id": "media-1",
    "createTime": "2024-06-15T14:30:00Z",
    "type": "PHOTO",
    "mediaFile": {
        "baseUrl": "https://lh3.googleusercontent.com/abc",
        "mimeType": "image/jpeg",
        "filename": "IMG_1234.jpg",
        "mediaFileMetadata": {"width": 4032, "height": 3024},
    },
}

_VIDEO_ITEM_JSON = {
    "id": "vid-1",
    "createTime": "2024-06-15T14:30:00Z",
    "type": "VIDEO",
    "mediaFile": {
        "baseUrl": "https://lh3.googleusercontent.com/vid",
        "mimeType": "video/mp4",
        "filename": "VID_1234.mp4",
        "mediaFileMetadata": {"width": 3840, "height": 2160},
    },
    "videoMetadata": {
        "cameraMake": "Google",
        "cameraModel": "Pixel 8",
        "fps": 30.0,
        "processingStatus": "READY",
    },
}


@pytest.fixture(autouse=True)
def _clear_cached_media_items_between_tests() -> Iterator[None]:
    _clear_media_items_cache()
    yield
    _clear_media_items_cache()


class TestResponseParsing:
    async def test_maps_response_to_domain_model(self) -> None:
        mock_client = async_client(post=json_response(_SESSION_JSON))

        session = await create_picker_session(mock_client, "test-token")

        assert isinstance(session, PickerSession)
        assert session.id == "session-xyz"
        assert session.picker_uri == "https://photos.google.com/picker/abc"
        assert session.polling_interval == "5s"

    async def test_propagates_http_error(self) -> None:
        error = httpx.Response(
            500, request=httpx.Request("POST", "http://test"), content=b"error"
        )
        mock_client = async_client(post=error)

        with pytest.raises(httpx.HTTPStatusError):
            await create_picker_session(mock_client, "test-token")


class TestGetMediaItems:
    async def test_single_page(self) -> None:
        page_json = {"mediaItems": [_MEDIA_ITEM_JSON]}
        mock_client = async_client(get=json_response(page_json))

        items = await get_media_items(mock_client, "session-1", "token-1")

        assert len(items) == 1
        assert isinstance(items[0], PickedMediaItem)
        assert items[0].id == "media-1"
        assert items[0].media_file.width == 4032
        assert items[0].media_file.filename == "IMG_1234.jpg"

    async def test_pagination_collects_all_pages(self) -> None:
        item2 = {**_MEDIA_ITEM_JSON, "id": "media-2"}
        page1 = json_response(
            {"mediaItems": [_MEDIA_ITEM_JSON], "nextPageToken": "page-2"}
        )
        page2 = json_response({"mediaItems": [item2]})
        mock_client = async_client(get=[page1, page2])

        items = await get_media_items(mock_client, "session-1", "token-1")

        assert len(items) == 2
        assert items[0].id == "media-1"
        assert items[1].id == "media-2"
        second_call_params = mock_client.get.call_args_list[1].kwargs.get("params", {})
        assert second_call_params.get("pageToken") == "page-2"

    async def test_video_processing_status_surfaced(self) -> None:
        mock_client = async_client(
            get=json_response({"mediaItems": [_VIDEO_ITEM_JSON]})
        )

        items = await get_media_items(mock_client, "session-1", "token-1")

        assert len(items) == 1
        assert items[0].type == "VIDEO"
        assert items[0].video_processing_status == "READY"


class TestCachedMediaItems:
    @staticmethod
    def _item() -> PickedMediaItem:
        return PickedMediaItem(
            id="google-photo",
            create_time="",
            type="PHOTO",
            media_file=GoogleMediaFile(
                base_url="https://lh3.googleusercontent.com/photo",
                mime_type="image/jpeg",
                filename="photo.jpg",
            ),
        )

    async def test_scopes_cache_to_user(self) -> None:
        client = AsyncMock()
        items = [self._item()]

        with patch(
            "app.services.google_photos.get_media_items",
            AsyncMock(return_value=items),
        ) as fetch:
            await get_media_items_cached(
                client,
                uid=1,
                session_id="session-1",
                access_token=_TOKEN,
            )
            await get_media_items_cached(
                client,
                uid=2,
                session_id="session-1",
                access_token=_TOKEN,
            )

        assert fetch.await_count == 2

    async def test_evicts_after_use(self) -> None:
        client = AsyncMock()
        items = [self._item()]

        with patch(
            "app.services.google_photos.get_media_items",
            AsyncMock(return_value=items),
        ) as fetch:
            await get_media_items_cached(
                client,
                uid=1,
                session_id="session-1",
                access_token=_TOKEN,
            )
            evict_cached_media_items(1, ["session-1"])
            await get_media_items_cached(
                client,
                uid=1,
                session_id="session-1",
                access_token=_TOKEN,
            )

        assert fetch.await_count == 2


def _oauth_mock(refresh_return: OAuth2Token | None = None) -> AsyncMock:
    mock = AsyncMock(spec=GoogleOAuth2)
    if refresh_return is not None:
        mock.refresh_token.return_value = refresh_return
    return mock


class TestEnsureFreshToken:
    async def test_returns_input_when_fresh(self) -> None:
        fresh = OAuth2Token({"access_token": "tok-fresh", "expires_in": 3600})
        oauth = _oauth_mock()
        result = await ensure_fresh_token(oauth, "rt-1", fresh)
        assert result is fresh
        oauth.refresh_token.assert_not_called()

    async def test_refreshes_when_stale_or_none(self) -> None:
        new = OAuth2Token({"access_token": "tok-new", "expires_in": 3600})
        oauth = _oauth_mock(refresh_return=new)

        result = await ensure_fresh_token(oauth, "rt-1", None)
        assert result is new

        stale = OAuth2Token({"access_token": "tok-stale", "expires_in": 0})
        result = await ensure_fresh_token(oauth, "rt-1", stale)
        assert result is new
        assert oauth.refresh_token.call_count == 2

    async def test_propagates_refresh_token_error(self) -> None:
        oauth = _oauth_mock()
        oauth.refresh_token.side_effect = RefreshTokenError("invalid_grant")
        with pytest.raises(RefreshTokenError):
            await ensure_fresh_token(oauth, "rt-bad", None)


_BASE_URL = "https://lh3.googleusercontent.com/test"
_TOKEN = "ya29.test"  # noqa: S105


def _streaming_client(
    chunks: list[bytes], headers: dict[str, str] | None = None
) -> AsyncMock:
    resp = AsyncMock()
    resp.raise_for_status = lambda: None
    resp.headers = headers or {}
    resp.aiter_bytes = lambda **_: _async_iter(chunks)

    @asynccontextmanager
    async def _stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[AsyncMock]:
        yield resp

    client = AsyncMock()
    client.stream = _stream
    return client


async def _async_iter(items: list[bytes]) -> AsyncIterator[bytes]:
    for item in items:
        yield item


class TestDownloadMediaBytes:
    async def test_writes_file_on_success(self, tmp_path: Path) -> None:
        dest = tmp_path / "photo.jpg"
        client = _streaming_client([b"photo-data"])
        await download_media_to_file(client, _BASE_URL, _TOKEN, dest, max_bytes=1000)
        assert dest.read_bytes() == b"photo-data"

    async def test_raises_on_size_limit(self, tmp_path: Path) -> None:
        dest = tmp_path / "photo.jpg"
        client = _streaming_client([b"x" * 600])
        with pytest.raises(DownloadTooLargeError):
            await download_media_to_file(client, _BASE_URL, _TOKEN, dest, max_bytes=500)

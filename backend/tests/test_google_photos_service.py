"""Tests for app.services.google_photos - Pydantic parsing and pagination.

Tests the API contract boundary: camelCase Google JSON -> domain models.
Uses real httpx.Response objects so Pydantic parsing runs end-to-end.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.google_photos import (
    DownloadTooLargeError,
    PickedMediaItem,
    PickerSession,
    TokenProvider,
    _MediaItemsPage,
    _SessionResponse,
    _TokenResponse,
    create_picker_session,
    download_media_bytes,
    download_media_to_file,
    get_media_items,
)

# ---------------------------------------------------------------------------
# Fixtures: realistic Google API JSON (camelCase, extra fields)
# ---------------------------------------------------------------------------

_SESSION_JSON = {
    "id": "session-xyz",
    "pickerUri": "https://photos.google.com/picker/abc",
    "pollingConfig": {"pollInterval": "5s"},
    "expireTime": "2025-01-01T00:00:00Z",  # extra field we don't model
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


# ---------------------------------------------------------------------------
# Response parsing (Pydantic camelCase -> snake_case)
# ---------------------------------------------------------------------------


class TestResponseParsing:
    def test_session_response_parses_camel_case(self) -> None:
        data = _SessionResponse.model_validate(_SESSION_JSON)
        assert data.id == "session-xyz"
        assert data.picker_uri == "https://photos.google.com/picker/abc"
        assert data.polling_config is not None
        assert data.polling_config.poll_interval == "5s"
        assert data.media_items_set is False

    def test_session_response_ignores_extra_fields(self) -> None:
        """Google may add fields; extra='allow' prevents breakage."""
        data = _SessionResponse.model_validate(_SESSION_JSON)
        assert data.id == "session-xyz"  # core fields still parsed

    def test_media_items_page_parses_items(self) -> None:
        raw = {"mediaItems": [_MEDIA_ITEM_JSON], "nextPageToken": "tok-2"}
        page = _MediaItemsPage.model_validate(raw)
        assert len(page.media_items) == 1
        assert page.media_items[0].id == "media-1"
        assert page.media_items[0].media_file.filename == "IMG_1234.jpg"
        assert page.media_items[0].media_file.media_file_metadata is not None
        assert page.media_items[0].media_file.media_file_metadata.width == 4032
        assert page.next_page_token == "tok-2"  # noqa: S105

    def test_media_items_page_defaults_on_empty(self) -> None:
        page = _MediaItemsPage.model_validate({})
        assert page.media_items == []
        assert page.next_page_token is None

    def test_token_response_parses_access_token(self) -> None:
        data = _TokenResponse.model_validate(
            {"access_token": "ya29.abc", "expires_in": 3599, "token_type": "Bearer"}
        )
        assert data.access_token == "ya29.abc"  # noqa: S105

    def test_media_item_without_metadata(self) -> None:
        """Some items may lack mediaFileMetadata."""
        raw = {**_MEDIA_ITEM_JSON, "mediaFile": {**_MEDIA_ITEM_JSON["mediaFile"]}}
        del raw["mediaFile"]["mediaFileMetadata"]
        page = _MediaItemsPage.model_validate({"mediaItems": [raw]})
        item = page.media_items[0]
        assert item.media_file.media_file_metadata is None


# ---------------------------------------------------------------------------
# Service function tests (mock HTTP, test logic + parsing end-to-end)
# ---------------------------------------------------------------------------


_DUMMY_REQUEST = httpx.Request("GET", "http://test")


def _json_response(data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code, content=json.dumps(data).encode(), request=_DUMMY_REQUEST
    )


class TestCreatePickerSession:
    async def test_maps_response_to_domain_model(self) -> None:
        mock_client = AsyncMock()
        mock_client.post.return_value = _json_response(_SESSION_JSON)

        with patch(
            "app.services.google_photos._picker_client", return_value=mock_client
        ):
            session = await create_picker_session("test-token")

        assert isinstance(session, PickerSession)
        assert session.id == "session-xyz"
        assert session.picker_uri == "https://photos.google.com/picker/abc"
        assert session.polling_interval == "5s"

    async def test_propagates_http_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.post.return_value = httpx.Response(
            500, request=httpx.Request("POST", "http://test"), content=b"error"
        )

        with (
            patch(
                "app.services.google_photos._picker_client", return_value=mock_client
            ),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await create_picker_session("test-token")


class TestGetMediaItems:
    async def test_single_page(self) -> None:
        page_json = {"mediaItems": [_MEDIA_ITEM_JSON]}

        mock_client = AsyncMock()
        mock_client.get.return_value = _json_response(page_json)

        with patch(
            "app.services.google_photos._picker_client", return_value=mock_client
        ):
            items = await get_media_items("session-1", "token-1")

        assert len(items) == 1
        assert isinstance(items[0], PickedMediaItem)
        assert items[0].id == "media-1"
        assert items[0].media_file.width == 4032
        assert items[0].media_file.filename == "IMG_1234.jpg"

    async def test_pagination_collects_all_pages(self) -> None:
        item2 = {**_MEDIA_ITEM_JSON, "id": "media-2"}
        page1 = _json_response(
            {"mediaItems": [_MEDIA_ITEM_JSON], "nextPageToken": "page-2"}
        )
        page2 = _json_response({"mediaItems": [item2]})

        mock_client = AsyncMock()
        mock_client.get.side_effect = [page1, page2]

        with patch(
            "app.services.google_photos._picker_client", return_value=mock_client
        ):
            items = await get_media_items("session-1", "token-1")

        assert len(items) == 2
        assert items[0].id == "media-1"
        assert items[1].id == "media-2"
        # Verify page token was passed on second call
        second_call_params = mock_client.get.call_args_list[1].kwargs.get("params", {})
        assert second_call_params.get("pageToken") == "page-2"

    async def test_empty_response(self) -> None:
        mock_client = AsyncMock()
        mock_client.get.return_value = _json_response({})

        with patch(
            "app.services.google_photos._picker_client", return_value=mock_client
        ):
            items = await get_media_items("session-1", "token-1")

        assert items == []

    async def test_video_items_preserved(self) -> None:
        """get_media_items returns all types; filtering is done later."""
        video = {**_MEDIA_ITEM_JSON, "id": "vid-1", "type": "VIDEO"}
        mock_client = AsyncMock()
        mock_client.get.return_value = _json_response({"mediaItems": [video]})

        with patch(
            "app.services.google_photos._picker_client", return_value=mock_client
        ):
            items = await get_media_items("session-1", "token-1")

        assert len(items) == 1
        assert items[0].type == "VIDEO"

    async def test_video_processing_status_surfaced(self) -> None:
        mock_client = AsyncMock()
        mock_client.get.return_value = _json_response(
            {"mediaItems": [_VIDEO_ITEM_JSON]}
        )

        with patch(
            "app.services.google_photos._picker_client", return_value=mock_client
        ):
            items = await get_media_items("session-1", "token-1")

        assert len(items) == 1
        assert items[0].type == "VIDEO"
        assert items[0].video_processing_status == "READY"


class TestVideoMetadataParsing:
    def test_video_processing_status_parsed(self) -> None:
        page = _MediaItemsPage.model_validate({"mediaItems": [_VIDEO_ITEM_JSON]})
        assert page.media_items[0].type == "VIDEO"

    def test_video_processing_status_surfaced_on_picked_item(self) -> None:
        """get_media_items should surface processingStatus on PickedMediaItem."""
        page = _MediaItemsPage.model_validate({"mediaItems": [_VIDEO_ITEM_JSON]})
        raw = page.media_items[0]
        assert raw.video_metadata is not None
        assert raw.video_metadata.processing_status == "READY"

    def test_photo_has_no_video_metadata(self) -> None:
        page = _MediaItemsPage.model_validate({"mediaItems": [_MEDIA_ITEM_JSON]})
        raw = page.media_items[0]
        assert raw.video_metadata is None


# ---------------------------------------------------------------------------
# TokenProvider
# ---------------------------------------------------------------------------


def _mock_refresh(token: str = "fresh-token") -> AsyncMock:  # noqa: S107
    """Return a mock that resolves to a _TokenResponse with the given token."""
    mock = AsyncMock()
    mock.return_value = _TokenResponse.model_validate(
        {"access_token": token, "expires_in": 3599, "token_type": "Bearer"}
    )
    return mock


class TestTokenProvider:
    async def test_returns_cached_token_within_margin(self) -> None:
        mock = _mock_refresh("tok-1")
        with patch("app.services.google_photos.refresh_access_token", mock):
            tp = TokenProvider("rt-1")
            t1 = await tp.get()
            t2 = await tp.get()
        assert t1 == "tok-1"
        assert t2 == "tok-1"
        assert mock.call_count == 1  # only one refresh

    async def test_refreshes_when_past_margin(self) -> None:
        call_count = 0

        async def _refresh(_rt: str) -> _TokenResponse:
            nonlocal call_count
            call_count += 1
            return _TokenResponse.model_validate({"access_token": f"tok-{call_count}"})

        with (
            patch("app.services.google_photos.refresh_access_token", _refresh),
            patch.object(TokenProvider, "_REFRESH_MARGIN", 0),  # expire immediately
        ):
            tp = TokenProvider("rt-1")
            t1 = await tp.get()
            t2 = await tp.get()
        assert t1 == "tok-1"
        assert t2 == "tok-2"
        assert call_count == 2

    async def test_marks_revoked_on_401(self) -> None:
        mock = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Unauthorized",
                request=httpx.Request("POST", "http://test"),
                response=httpx.Response(401),
            )
        )
        with patch("app.services.google_photos.refresh_access_token", mock):
            tp = TokenProvider("rt-bad")
            with pytest.raises(httpx.HTTPStatusError):
                await tp.get()
            # Subsequent calls raise RuntimeError, not HTTP error
            with pytest.raises(RuntimeError, match="revoked"):
                await tp.get()

    async def test_concurrent_gets_serialize(self) -> None:
        """Two concurrent .get() calls should only trigger one refresh."""
        mock = _mock_refresh("tok-shared")
        with patch("app.services.google_photos.refresh_access_token", mock):
            tp = TokenProvider("rt-1")
            t1, t2 = await asyncio.gather(tp.get(), tp.get())
        assert t1 == t2 == "tok-shared"
        assert mock.call_count == 1


# ---------------------------------------------------------------------------
# Download size limits and cleanup
# ---------------------------------------------------------------------------

_BASE_URL = "https://lh3.googleusercontent.com/test"
_TOKEN = "ya29.test"  # noqa: S105


def _streaming_client(
    chunks: list[bytes], headers: dict[str, str] | None = None
) -> AsyncMock:
    """Build a mock httpx.AsyncClient whose .stream() yields the given chunks."""
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
    async def test_rejects_content_length_over_limit(self) -> None:
        client = _streaming_client([], headers={"content-length": "1000"})
        with (
            patch("app.services.google_photos._download_client", return_value=client),
            pytest.raises(DownloadTooLargeError),
        ):
            await download_media_bytes(_BASE_URL, _TOKEN, max_bytes=500)

    async def test_rejects_stream_exceeding_limit(self) -> None:
        """Even without content-length, reject if chunks exceed max_bytes."""
        client = _streaming_client([b"x" * 600])
        with (
            patch("app.services.google_photos._download_client", return_value=client),
            pytest.raises(DownloadTooLargeError),
        ):
            await download_media_bytes(_BASE_URL, _TOKEN, max_bytes=500)

    async def test_accepts_within_limit(self) -> None:
        client = _streaming_client([b"hello"])
        with patch("app.services.google_photos._download_client", return_value=client):
            result = await download_media_bytes(_BASE_URL, _TOKEN, max_bytes=1000)
        assert result == b"hello"


class TestDownloadMediaToFile:
    async def test_cleans_up_partial_file_on_size_limit(self, tmp_path: Path) -> None:
        dest = tmp_path / "photo.jpg"
        client = _streaming_client([b"x" * 600])
        with (
            patch("app.services.google_photos._download_client", return_value=client),
            pytest.raises(DownloadTooLargeError),
        ):
            await download_media_to_file(_BASE_URL, _TOKEN, dest, max_bytes=500)
        assert not dest.exists(), "Partial file should be cleaned up"

    async def test_cleans_up_on_http_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "photo.jpg"

        def _raise() -> None:
            raise httpx.HTTPStatusError(
                "Server Error",
                request=httpx.Request("GET", "http://test"),
                response=httpx.Response(500),
            )

        resp = AsyncMock()
        resp.raise_for_status = _raise
        resp.headers = {}

        @asynccontextmanager
        async def _stream(*_a: Any, **_kw: Any) -> AsyncIterator[AsyncMock]:
            yield resp

        client = AsyncMock()
        client.stream = _stream
        with (
            patch("app.services.google_photos._download_client", return_value=client),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await download_media_to_file(_BASE_URL, _TOKEN, dest)
        assert not dest.exists(), "File should be cleaned up on HTTP error"

    async def test_writes_file_on_success(self, tmp_path: Path) -> None:
        dest = tmp_path / "photo.jpg"
        client = _streaming_client([b"photo-data"])
        with patch("app.services.google_photos._download_client", return_value=client):
            await download_media_to_file(_BASE_URL, _TOKEN, dest, max_bytes=1000)
        assert dest.read_bytes() == b"photo-data"

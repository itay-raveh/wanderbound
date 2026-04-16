"""Tests for app.services.google_photos - Pydantic parsing and pagination.

Tests the API contract boundary: camelCase Google JSON -> domain models.
Uses real httpx.Response objects so Pydantic parsing runs end-to-end.
"""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.google_photos import (
    PickedMediaItem,
    PickerSession,
    _MediaItemsPage,
    _SessionResponse,
    _TokenResponse,
    create_picker_session,
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

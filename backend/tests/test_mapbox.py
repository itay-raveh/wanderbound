"""Tests for app.services.mapbox — Mapbox Map Matching & Directions API client."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.mapbox import (
    _chunked_route,
    _fetch_directions,
    _fetch_matching,
    match_segment,
    match_segments,
)

type Coords = list[tuple[float, float]]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _matching_json(coords: list[list[float]]) -> bytes:
    return json.dumps(
        {
            "matchings": [{"geometry": {"type": "LineString", "coordinates": coords}}],
        }
    ).encode()


def _directions_json(coords: list[list[float]]) -> bytes:
    return json.dumps(
        {
            "routes": [{"geometry": {"type": "LineString", "coordinates": coords}}],
        }
    ).encode()


def _error_response(status: int = 422) -> MagicMock:
    return MagicMock(status_code=status)


def _ok_response(content: bytes) -> MagicMock:
    resp = MagicMock(status_code=200)
    resp.content = content
    return resp


# ---------------------------------------------------------------------------
# _fetch_matching — coordinate extraction + stitching logic
# ---------------------------------------------------------------------------


class TestFetchMatching:
    async def test_api_error_returns_none(self) -> None:
        client = AsyncMock()
        client.get.return_value = _error_response(500)
        assert (
            await _fetch_matching(client, [(4.0, 52.0), (4.1, 52.1)], "driving", "tok")
            is None
        )

    async def test_empty_matchings_returns_none(self) -> None:
        client = AsyncMock()
        client.get.return_value = _ok_response(b'{"matchings": []}')
        assert (
            await _fetch_matching(client, [(4.0, 52.0), (4.1, 52.1)], "driving", "tok")
            is None
        )

    async def test_single_point_returns_none(self) -> None:
        client = AsyncMock()
        client.get.return_value = _ok_response(_matching_json([[4.0, 52.0]]))
        assert await _fetch_matching(client, [(4.0, 52.0)], "driving", "tok") is None

    async def test_multiple_matchings_stitched(self) -> None:
        """First point of subsequent matchings is skipped to avoid duplication."""
        client = AsyncMock()
        content = json.dumps(
            {
                "matchings": [
                    {
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[1, 2], [3, 4]],
                        }
                    },
                    {
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[5, 6], [7, 8]],
                        }
                    },
                ]
            }
        ).encode()
        client.get.return_value = _ok_response(content)
        result = await _fetch_matching(client, [(1, 2), (7, 8)], "driving", "tok")
        assert result == [(1, 2), (3, 4), (7, 8)]


# ---------------------------------------------------------------------------
# _fetch_directions
# ---------------------------------------------------------------------------


class TestFetchDirections:
    async def test_api_error_returns_none(self) -> None:
        client = AsyncMock()
        client.get.return_value = _error_response(500)
        assert (
            await _fetch_directions(
                client, [(4.0, 52.0), (4.1, 52.1)], "walking", "tok"
            )
            is None
        )

    async def test_empty_routes_returns_none(self) -> None:
        client = AsyncMock()
        client.get.return_value = _ok_response(b'{"routes": []}')
        assert (
            await _fetch_directions(
                client, [(4.0, 52.0), (4.1, 52.1)], "walking", "tok"
            )
            is None
        )

    async def test_single_point_returns_none(self) -> None:
        client = AsyncMock()
        client.get.return_value = _ok_response(_directions_json([[4.0, 52.0]]))
        assert await _fetch_directions(client, [(4.0, 52.0)], "walking", "tok") is None


# ---------------------------------------------------------------------------
# _chunked_route
# ---------------------------------------------------------------------------


class TestChunkedRoute:
    async def test_stitches_chunks(self) -> None:
        coords: Coords = [(i * 0.01, 52.0) for i in range(10)]
        call_count = 0

        async def mock_fn(chunk: Coords) -> Coords:
            nonlocal call_count
            call_count += 1
            return [(c[0], c[1] + 0.001) for c in chunk]

        result = await _chunked_route(coords, chunk_size=4, overlap=1, route_fn=mock_fn)
        assert result is not None
        assert call_count == 3
        # First point preserved, subsequent chunks skip first point
        assert result[0] == (0.0, 52.001)

    async def test_all_chunks_fail(self) -> None:
        coords: Coords = [(i * 0.01, 52.0) for i in range(10)]

        async def fail_fn(_: Coords) -> None:
            return None

        result = await _chunked_route(coords, chunk_size=4, overlap=1, route_fn=fail_fn)
        assert result is None

    async def test_partial_failure(self) -> None:
        """If some chunks fail, remaining are still stitched."""
        call_idx = 0

        async def partial_fn(chunk: Coords) -> Coords | None:
            nonlocal call_idx
            call_idx += 1
            if call_idx == 2:
                return None  # second chunk fails
            return [(c[0], c[1] + 0.001) for c in chunk]

        coords: Coords = [(i * 0.01, 52.0) for i in range(10)]
        result = await _chunked_route(
            coords, chunk_size=4, overlap=1, route_fn=partial_fn
        )
        assert result is not None
        assert len(result) >= 2


# ---------------------------------------------------------------------------
# match_segment (integration, mocked HTTP)
# ---------------------------------------------------------------------------


class TestMatchSegment:
    async def test_too_few_points(self) -> None:
        result = await match_segment([(4.0, 52.0)], "driving")
        assert result is None

    @patch("app.services.mapbox.get_settings")
    async def test_no_token(self, mock_settings: MagicMock) -> None:
        mock_settings.return_value.MAPBOX_TOKEN = ""
        result = await match_segment([(4.0, 52.0), (4.1, 52.1)], "driving")
        assert result is None

    @patch("app.services.mapbox._client")
    @patch("app.services.mapbox.get_settings")
    async def test_dense_uses_matching(
        self, mock_settings: MagicMock, mock_client_fn: MagicMock
    ) -> None:
        mock_settings.return_value.MAPBOX_TOKEN = "test-token"  # noqa: S105
        coords: Coords = [(4.0 + i * 0.001, 52.0) for i in range(10)]
        route_coords = [[c[0], c[1]] for c in coords]

        mock_client = AsyncMock()
        mock_client.get.return_value = _ok_response(_matching_json(route_coords))
        mock_client_fn.return_value = mock_client

        result = await match_segment(coords, "driving")
        assert result is not None
        url = mock_client.get.call_args[0][0]
        assert "/matching/" in url

    @patch("app.services.mapbox._client")
    @patch("app.services.mapbox.get_settings")
    async def test_sparse_uses_directions(
        self, mock_settings: MagicMock, mock_client_fn: MagicMock
    ) -> None:
        mock_settings.return_value.MAPBOX_TOKEN = "test-token"  # noqa: S105
        coords: Coords = [(4.0, 52.0), (5.0, 52.0), (6.0, 52.0)]
        route_coords = [[c[0], c[1]] for c in coords]

        mock_client = AsyncMock()
        mock_client.get.return_value = _ok_response(_directions_json(route_coords))
        mock_client_fn.return_value = mock_client

        result = await match_segment(coords, "driving")
        assert result is not None
        url = mock_client.get.call_args[0][0]
        assert "/directions/" in url


# ---------------------------------------------------------------------------
# match_segments (batch, shared client)
# ---------------------------------------------------------------------------


class TestMatchSegments:
    async def test_empty_list(self) -> None:
        result = await match_segments([])
        assert result == []

    @patch("app.services.mapbox.get_settings")
    async def test_no_token(self, mock_settings: MagicMock) -> None:
        mock_settings.return_value.MAPBOX_TOKEN = ""
        result = await match_segments(
            [
                ([(4.0, 52.0), (4.1, 52.1)], "driving"),
                ([(5.0, 52.0), (5.1, 52.1)], "walking"),
            ]
        )
        assert result == [None, None]

    @patch("app.services.mapbox._client")
    @patch("app.services.mapbox.get_settings")
    async def test_shared_client(
        self, mock_settings: MagicMock, mock_client_fn: MagicMock
    ) -> None:
        """All segments in a batch share one cached client."""
        mock_settings.return_value.MAPBOX_TOKEN = "test-token"  # noqa: S105
        coords_a: Coords = [(4.0 + i * 0.001, 52.0) for i in range(5)]
        coords_b: Coords = [(5.0 + i * 0.001, 52.0) for i in range(5)]

        mock_client = AsyncMock()
        mock_client.get.return_value = _ok_response(
            _matching_json([[4.0, 52.0], [4.1, 52.1]])
        )
        mock_client_fn.return_value = mock_client

        results = await match_segments([(coords_a, "driving"), (coords_b, "walking")])
        assert len(results) == 2

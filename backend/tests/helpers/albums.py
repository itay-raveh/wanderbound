from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from tests.factories import AID

if TYPE_CHECKING:
    from httpx import AsyncClient, Response


@dataclass(frozen=True)
class AlbumRoutes:
    client: AsyncClient

    async def get_album(self, aid: str = AID) -> Response:
        return await self.client.get(f"/api/v1/albums/{aid}")

    async def get_segments(self, aid: str = AID) -> Response:
        return await self.client.get(f"/api/v1/albums/{aid}/segments")

    async def get_steps(self, aid: str = AID) -> Response:
        return await self.client.get(f"/api/v1/albums/{aid}/steps")

    async def get_media(self, aid: str = AID) -> Response:
        return await self.client.get(f"/api/v1/albums/{aid}/media")

    async def get_segment_points(
        self,
        *,
        from_time: float = 0.0,
        to_time: float = 1000.0,
    ) -> tuple[Response, MagicMock]:
        with patch(
            "app.api.v1.routes.albums.enqueue_album_route_enrichment",
        ) as mock_enqueue:
            resp = await self.client.get(
                f"/api/v1/albums/{AID}/segments/points",
                params={"from_time": from_time, "to_time": to_time},
            )
        return resp, mock_enqueue

    async def get_segment_points_ok(
        self,
        *,
        from_time: float = 0.0,
        to_time: float = 1000.0,
    ) -> tuple[list, MagicMock]:
        resp, mock_enqueue = await self.get_segment_points(
            from_time=from_time,
            to_time=to_time,
        )
        assert resp.status_code == 200
        return resp.json(), mock_enqueue

    async def update_album(self, **payload: object) -> Response:
        return await self.client.patch(f"/api/v1/albums/{AID}", json=payload)

    async def update_album_ok(self, **payload: object) -> dict:
        resp = await self.update_album(**payload)
        assert resp.status_code == 200
        return resp.json()

    async def update_step(self, step_id: int = 1, **payload: object) -> Response:
        return await self.client.patch(
            f"/api/v1/albums/{AID}/steps/{step_id}",
            json=payload,
        )

    async def update_media_layout(
        self,
        *,
        step_id: int = 1,
        cover: str | None,
        pages: list[list[str]],
        unused: list[str],
    ) -> Response:
        return await self.client.put(
            f"/api/v1/albums/{AID}/steps/{step_id}/media-layout",
            json={"cover": cover, "pages": pages, "unused": unused},
        )

    async def adjust_boundary(
        self,
        *,
        start_time: float = 100.0,
        end_time: float = 300.0,
        new_boundary_time: float = 200.0,
        handle: str = "end",
    ) -> Response:
        return await self.client.patch(
            f"/api/v1/albums/{AID}/segments/adjust-boundary",
            json={
                "start_time": start_time,
                "end_time": end_time,
                "new_boundary_time": new_boundary_time,
                "handle": handle,
            },
        )

    async def adjust_boundary_ok(
        self,
        *,
        start_time: float = 100.0,
        end_time: float = 300.0,
        new_boundary_time: float = 200.0,
        handle: str = "end",
    ) -> list:
        resp = await self.adjust_boundary(
            start_time=start_time,
            end_time=end_time,
            new_boundary_time=new_boundary_time,
            handle=handle,
        )
        assert resp.status_code == 200
        return resp.json()

    async def print_bundle(self, *, chapter: str | None = None) -> Response:
        params = {} if chapter is None else {"chapter": chapter}
        return await self.client.get(
            f"/api/v1/albums/{AID}/print-bundle",
            params=params,
        )

    async def download_pdf(self, token: str) -> Response:
        return await self.client.get(f"/api/v1/albums/pdf/download/{token}")

    async def generate_chapters_pdf(
        self,
        aid: str = AID,
        *,
        chapters: list[str] | None = None,
    ) -> Response:
        params = [("chapters", chapter) for chapter in chapters or []]
        return await self.client.post(
            f"/api/v1/albums/{aid}/pdf/generate-chapters",
            params=params,
        )

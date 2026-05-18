from __future__ import annotations

import io
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PIL import Image

from tests.factories import AID, DEFAULT_MEDIA_NAME, AlbumMediaScenario

if TYPE_CHECKING:
    from httpx import AsyncClient, Response

AlbumMediaFactory = Callable[..., Awaitable[AlbumMediaScenario]]


def jpeg_bytes(width: int = 640, height: int = 480) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="red").save(buf, "JPEG")
    return buf.getvalue()


def download_guard() -> tuple[Callable[..., AsyncIterator[object]], Callable[[], bool]]:
    downloaded = False

    async def fail_if_downloaded(**_kwargs: object) -> AsyncIterator[object]:
        nonlocal downloaded
        downloaded = True
        for item in ():
            yield item

    return fail_if_downloaded, lambda: downloaded


@dataclass(frozen=True)
class ExternalMediaRoutes:
    client: AsyncClient

    async def add_device(
        self,
        *,
        context: str,
        filename: str = "holiday.jpg",
        step_id: int | None = None,
        width: int = 640,
        height: int = 480,
    ) -> Response:
        data: dict[str, str] = {"context": context}
        if step_id is not None:
            data["step_id"] = str(step_id)
        return await self.client.post(
            f"/api/v1/albums/{AID}/external-media/add/device",
            data=data,
            files=[("files", (filename, jpeg_bytes(width, height), "image/jpeg"))],
        )

    async def add_device_ok(
        self,
        *,
        context: str,
        filename: str = "holiday.jpg",
        step_id: int | None = None,
        width: int = 640,
        height: int = 480,
    ) -> dict:
        resp = await self.add_device(
            context=context,
            filename=filename,
            step_id=step_id,
            width=width,
            height=height,
        )
        assert resp.status_code == 200
        return resp.json()

    async def replace_device(
        self,
        media_name: str,
        *,
        width: int = 1200,
        height: int = 800,
        content: bytes | None = None,
    ) -> Response:
        body = content if content is not None else jpeg_bytes(width, height)
        return await self.client.post(
            f"/api/v1/albums/{AID}/external-media/replace/device",
            data={"media_name": media_name},
            files={"file": ("replacement.jpg", body, "image/jpeg")},
        )

    async def replace_device_ok(
        self,
        media_name: str,
        *,
        width: int = 1200,
        height: int = 800,
        content: bytes | None = None,
    ) -> dict:
        resp = await self.replace_device(
            media_name,
            width=width,
            height=height,
            content=content,
        )
        assert resp.status_code == 200
        return resp.json()

    async def undo_replacement(self, media_name: str) -> Response:
        return await self.client.post(
            f"/api/v1/albums/{AID}/external-media/undo/{media_name}",
        )

    async def undo_replacement_ok(self, media_name: str) -> dict:
        resp = await self.undo_replacement(media_name)
        assert resp.status_code == 200
        return resp.json()

    async def replace_google(
        self,
        *,
        media_name: str = DEFAULT_MEDIA_NAME,
        session_id: str = "session-abc",
    ) -> Response:
        return await self.client.post(
            f"/api/v1/albums/{AID}/external-media/replace/google",
            json={"media_name": media_name, "session_id": session_id},
        )

    async def replace_google_ok(
        self,
        *,
        media_name: str = DEFAULT_MEDIA_NAME,
        session_id: str = "session-abc",
    ) -> dict:
        resp = await self.replace_google(media_name=media_name, session_id=session_id)
        assert resp.status_code == 200
        return resp.json()

    async def add_google(
        self,
        **payload: str | int,
    ) -> Response:
        return await self.client.post(
            f"/api/v1/albums/{AID}/external-media/add/google",
            json={"session_id": "session-abc", **payload},
        )

    async def add_google_ok(self, **payload: str | int) -> str:
        resp = await self.add_google(**payload)
        assert resp.status_code == 200
        return resp.text

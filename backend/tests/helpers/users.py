from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tests.factories import (
    mock_extract,
    sign_in as factory_sign_in,
    sign_in_and_upload as factory_sign_in_and_upload,
)

if TYPE_CHECKING:
    from pathlib import Path

    from httpx import AsyncClient, Response


@dataclass(frozen=True)
class UserRoutes:
    client: AsyncClient

    async def auth(self, provider: str, credential: str = "fake") -> Response:
        return await self.client.post(
            f"/api/v1/auth/{provider}", json={"credential": credential}
        )

    async def sign_in(
        self, provider: str = "google", payload: dict | None = None
    ) -> None:
        await factory_sign_in(self.client, provider=provider, payload=payload)

    async def sign_in_and_upload(
        self,
        users_dir: Path,
        provider: str = "google",
        payload: dict | None = None,
    ) -> dict:
        return await factory_sign_in_and_upload(
            self.client, users_dir, provider=provider, payload=payload
        )

    async def logout(self) -> Response:
        return await self.client.post("/api/v1/auth/logout")

    async def upload(self) -> Response:
        return await self.client.post(
            "/api/v1/users/upload",
            files={"file": ("data.zip", b"fake", "application/zip")},
        )

    async def upload_with_extract(self, users_dir: Path) -> Response:
        with mock_extract(users_dir):
            return await self.upload()

    async def current(self) -> Response:
        return await self.client.get("/api/v1/users")

    async def update(self, **payload: object) -> Response:
        return await self.client.patch("/api/v1/users", json=payload)

    async def delete(self) -> Response:
        return await self.client.delete("/api/v1/users")

    async def demo(self, *, accept_language: str | None = None) -> Response:
        headers = (
            {"Accept-Language": accept_language}
            if accept_language is not None
            else None
        )
        return await self.client.post("/api/v1/users/demo", headers=headers)

    async def delete_demo(self) -> Response:
        return await self.client.delete("/api/v1/users/demo")

    async def init_upload(self) -> Response:
        return await self.client.post("/api/v1/users/upload/init")

    async def start_chunked_upload(self, provider: str = "google") -> str:
        await factory_sign_in(self.client, provider)
        resp = await self.init_upload()
        assert resp.status_code == 200
        return resp.json()["upload_id"]

    async def put_chunk(
        self,
        upload_id: str,
        index: int,
        content: bytes = b"fake-zip",
    ) -> Response:
        return await self.client.put(
            f"/api/v1/users/upload/{upload_id}/{index}",
            content=content,
        )

    async def put_chunk_ok(
        self,
        upload_id: str,
        index: int,
        content: bytes = b"fake-zip",
    ) -> None:
        resp = await self.put_chunk(upload_id, index, content)
        assert resp.status_code == 204

    async def complete_upload(self, upload_id: str) -> Response:
        return await self.client.post(f"/api/v1/users/upload/{upload_id}/complete")

    async def complete_upload_with_extract(
        self,
        upload_id: str,
        users_dir: Path,
    ) -> Response:
        with mock_extract(users_dir):
            return await self.complete_upload(upload_id)

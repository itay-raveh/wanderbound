from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tests.factories import (
    sign_in as factory_sign_in,
    sign_in_user as factory_sign_in_user,
)

if TYPE_CHECKING:
    from pathlib import Path

    from httpx import AsyncClient, Response
    from sqlmodel.ext.asyncio.session import AsyncSession


@dataclass(frozen=True)
class UserRoutes:
    client: AsyncClient
    session: AsyncSession

    async def auth(self, provider: str, credential: str = "fake") -> Response:
        return await self.client.post(
            f"/api/v1/auth/{provider}", json={"credential": credential}
        )

    async def auth_ok(self, provider: str, credential: str = "fake") -> dict | None:
        resp = await self.auth(provider, credential)
        assert resp.status_code == 200
        return resp.json()

    async def sign_in(
        self, provider: str = "google", payload: dict | None = None
    ) -> None:
        await factory_sign_in(self.client, provider=provider, payload=payload)

    async def sign_in_user(
        self,
        users_dir: Path,
        provider: str = "google",
        payload: dict | None = None,
    ) -> dict:
        return await factory_sign_in_user(
            self.client,
            self.session,
            users_dir,
            provider=provider,
            payload=payload,
        )

    async def logout(self) -> Response:
        return await self.client.post("/api/v1/auth/logout")

    async def current(self) -> Response:
        return await self.client.get("/api/v1/users")

    async def current_ok(self) -> dict:
        resp = await self.current()
        assert resp.status_code == 200
        return resp.json()

    async def update(self, **payload: object) -> Response:
        return await self.client.patch("/api/v1/users", json=payload)

    async def delete(self) -> Response:
        return await self.client.delete("/api/v1/users")

    async def delete_ok(self) -> dict:
        resp = await self.delete()
        assert resp.status_code == 200
        return resp.json()

    async def demo(self, *, accept_language: str | None = None) -> Response:
        headers = (
            {"Accept-Language": accept_language}
            if accept_language is not None
            else None
        )
        return await self.client.post("/api/v1/users/demo", headers=headers)

    async def demo_ok(self, *, accept_language: str | None = None) -> dict:
        resp = await self.demo(accept_language=accept_language)
        assert resp.status_code == 200
        return resp.json()

    async def delete_demo(self) -> Response:
        return await self.client.delete("/api/v1/users/demo")

    async def download_export(self, token: str) -> Response:
        return await self.client.get(f"/api/v1/users/export/download/{token}")

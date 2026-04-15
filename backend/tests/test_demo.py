from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from httpx import AsyncClient


class TestCreateDemo:
    async def test_creates_demo_user(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/users/demo")
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["is_demo"] is True
        assert len(body["trips"]) >= 1

    async def test_sets_session_cookie(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/users/demo")
        uid = resp.json()["user"]["id"]
        user_resp = await client.get("/api/v1/users")
        assert user_resp.status_code == 200
        assert user_resp.json()["id"] == uid


class TestDeleteDemo:
    async def test_deletes_demo_user(self, client: AsyncClient) -> None:
        await client.post("/api/v1/users/demo")
        resp = await client.delete("/api/v1/users/demo")
        assert resp.status_code == 204
        # Session cleared - user endpoint returns 401
        user_resp = await client.get("/api/v1/users")
        assert user_resp.status_code == 401

    async def test_rejects_unauthenticated(self, client: AsyncClient) -> None:
        resp = await client.delete("/api/v1/users/demo")
        assert resp.status_code == 401

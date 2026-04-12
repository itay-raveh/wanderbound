from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from httpx import AsyncClient


class TestDemoLocale:
    async def test_demo_respects_accept_language(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/users/demo",
            headers={"Accept-Language": "he-IL,he;q=0.9,en;q=0.8"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["locale"] == "he-IL"

    async def test_demo_falls_back_to_fixture_locale(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/users/demo")
        assert resp.status_code == 200
        data = resp.json()
        # Fixture user.json has locale "en_GB" → normalized to "en-GB"
        assert data["user"]["locale"] == "en-GB"

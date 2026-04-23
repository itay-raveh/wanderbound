from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from app.models.user import User
from tests.factories import insert_album, sign_in_and_upload

if TYPE_CHECKING:
    from pathlib import Path

    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


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


class TestIsProcessed:
    """is_processed reflects whether albums in DB match the album_ids manifest."""

    async def test_demo_user_starts_unprocessed(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/users/demo")
        body = resp.json()
        assert body["user"]["has_data"] is True
        assert body["user"]["album_ids"]
        assert body["user"]["is_processed"] is False

    async def test_uploaded_user_starts_unprocessed(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        user = await sign_in_and_upload(client, tmp_path / "users")
        assert user["has_data"] is True
        assert user["album_ids"]
        assert user["is_processed"] is False

    async def test_processed_when_albums_exist(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        user = await sign_in_and_upload(client, tmp_path / "users")
        for aid in user["album_ids"]:
            await insert_album(session, user["id"], aid=aid)
        await session.commit()

        resp = await client.get("/api/v1/users")
        assert resp.status_code == 200
        assert resp.json()["is_processed"] is True

    async def test_evicted_user_is_unprocessed(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        user = await sign_in_and_upload(client, tmp_path / "users")
        for aid in user["album_ids"]:
            await insert_album(session, user["id"], aid=aid)
        await session.commit()
        shutil.rmtree(tmp_path / "users" / str(user["id"]))

        resp = await client.get("/api/v1/users")
        assert resp.json()["is_processed"] is False
        assert resp.json()["has_data"] is False

    async def test_partial_processing_is_unprocessed(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        user = await sign_in_and_upload(client, tmp_path / "users")
        u = await session.get(User, user["id"])
        assert u is not None
        u.album_ids = [user["album_ids"][0], "second-trip"]
        session.add(u)
        await session.commit()
        await insert_album(session, user["id"], aid=user["album_ids"][0])
        await session.commit()

        resp = await client.get("/api/v1/users")
        assert resp.json()["is_processed"] is False

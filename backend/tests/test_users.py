from __future__ import annotations

import shutil
from typing import TYPE_CHECKING
from unittest.mock import patch

from app.logic.trip_processing import ErrorData, PhaseUpdate, ProcessingEvent
from app.models.user import User
from tests.factories import insert_album, sign_in_and_upload

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
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


class TestProcessUser:
    async def test_enqueues_route_enrichment_after_successful_process_stream(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        user = await sign_in_and_upload(client, tmp_path / "users")
        db_user = await session.get(User, user["id"])
        assert db_user is not None
        db_user.album_ids = ["trip-1", "trip-2"]
        session.add(db_user)
        await session.commit()

        order: list[str] = []

        async def fake_process_stream(*_args: object) -> AsyncIterator[ProcessingEvent]:
            order.append("stream-start")
            yield PhaseUpdate(phase="layouts", done=1, total=1)
            order.append("stream-end")

        def enqueue(*args: object) -> None:
            order.append(f"enqueue-{args[3]}")

        with (
            patch("app.api.v1.routes.users.process_stream", fake_process_stream),
            patch(
                "app.api.v1.routes.users.enqueue_album_route_enrichment",
                side_effect=enqueue,
            ) as mock_enqueue,
        ):
            resp = await client.get("/api/v1/users/process")

        assert resp.status_code == 200
        assert order == [
            "stream-start",
            "stream-end",
            "enqueue-trip-1",
            "enqueue-trip-2",
        ]
        assert mock_enqueue.call_count == 2
        assert [call.args[2:] for call in mock_enqueue.call_args_list] == [
            (user["id"], "trip-1"),
            (user["id"], "trip-2"),
        ]

    async def test_does_not_enqueue_route_enrichment_after_process_error(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        await sign_in_and_upload(client, tmp_path / "users")

        async def fake_process_stream(*_args: object) -> AsyncIterator[ProcessingEvent]:
            yield ErrorData()

        with (
            patch("app.api.v1.routes.users.process_stream", fake_process_stream),
            patch("app.api.v1.routes.users.enqueue_album_route_enrichment") as enqueue,
        ):
            resp = await client.get("/api/v1/users/process")

        assert resp.status_code == 200
        enqueue.assert_not_called()

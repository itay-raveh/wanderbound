from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from app.models.user import User
from tests.factories import insert_album
from tests.helpers.users import UserRoutes

if TYPE_CHECKING:
    from pathlib import Path

    from sqlmodel.ext.asyncio.session import AsyncSession


async def _insert_uploaded_albums(
    session: AsyncSession,
    uploaded_user: dict,
) -> None:
    for aid in uploaded_user["album_ids"]:
        await insert_album(session, uploaded_user["id"], aid=aid)
        user = await session.get_one(User, uploaded_user["id"])
        (user.trips_folder / aid).mkdir(parents=True, exist_ok=True)
    await session.commit()


class TestDemoLocale:
    async def test_demo_respects_accept_language(self, user_routes: UserRoutes) -> None:
        data = await user_routes.demo_ok(accept_language="he-IL,he;q=0.9,en;q=0.8")
        assert data["user"]["locale"] == "he-IL"

    async def test_demo_falls_back_to_fixture_locale(
        self, user_routes: UserRoutes
    ) -> None:
        data = await user_routes.demo_ok()
        # Fixture user.json has locale "en_GB" → normalized to "en-GB"
        assert data["user"]["locale"] == "en-GB"


class TestIsProcessed:
    """is_processed reflects whether albums in DB match the album_ids manifest."""

    async def test_demo_user_starts_unprocessed(self, user_routes: UserRoutes) -> None:
        body = await user_routes.demo_ok()
        assert body["user"]["has_data"] is True
        assert body["user"]["album_ids"]
        assert body["user"]["is_processed"] is False

    async def test_uploaded_user_starts_unprocessed(self, uploaded_user: dict) -> None:
        assert uploaded_user["has_data"] is True
        assert uploaded_user["album_ids"]
        assert uploaded_user["is_processed"] is False

    async def test_processed_when_albums_exist(
        self,
        session: AsyncSession,
        user_routes: UserRoutes,
        uploaded_user: dict,
    ) -> None:
        await _insert_uploaded_albums(session, uploaded_user)

        assert (await user_routes.current_ok())["is_processed"] is True

    async def test_evicted_user_is_unprocessed(
        self,
        session: AsyncSession,
        user_routes: UserRoutes,
        users_dir: Path,
        uploaded_user: dict,
    ) -> None:
        await _insert_uploaded_albums(session, uploaded_user)
        shutil.rmtree(users_dir / str(uploaded_user["id"]))

        user = await user_routes.current_ok()
        assert user["is_processed"] is False
        assert user["has_data"] is False

    async def test_one_evicted_album_does_not_hide_available_albums(
        self,
        session: AsyncSession,
        user_routes: UserRoutes,
        users_dir: Path,
        uploaded_user: dict,
    ) -> None:
        uid = uploaded_user["id"]
        first = uploaded_user["album_ids"][0]
        db_user = await session.get_one(User, uid)
        db_user.album_ids = [first, "second-trip"]
        session.add(db_user)
        await insert_album(session, uid, aid=first)
        await insert_album(session, uid, aid="second-trip")
        await session.commit()
        (users_dir / str(uid) / "trip" / first).mkdir(parents=True, exist_ok=True)
        (users_dir / str(uid) / "trip" / "second-trip").mkdir(
            parents=True, exist_ok=True
        )
        shutil.rmtree(users_dir / str(uid) / "trip" / first)

        user = await user_routes.current_ok()

        assert user["album_ids"] == ["second-trip"]
        assert user["has_data"] is True
        assert user["is_processed"] is True

    async def test_partial_processing_is_unprocessed(
        self,
        session: AsyncSession,
        user_routes: UserRoutes,
        uploaded_user: dict,
    ) -> None:
        u = await session.get(User, uploaded_user["id"])
        assert u is not None
        u.album_ids = [uploaded_user["album_ids"][0], "second-trip"]
        session.add(u)
        await session.commit()
        await insert_album(
            session, uploaded_user["id"], aid=uploaded_user["album_ids"][0]
        )
        await session.commit()

        assert (await user_routes.current_ok())["is_processed"] is False

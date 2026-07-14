from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers.users import UserRoutes

if TYPE_CHECKING:
    from pathlib import Path

    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture
def user_routes(client: AsyncClient, session: AsyncSession) -> UserRoutes:
    return UserRoutes(client, session)


@pytest.fixture
async def uploaded_user(user_routes: UserRoutes, users_dir: Path) -> dict:
    return await user_routes.sign_in_user(users_dir)

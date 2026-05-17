from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers.users import UserRoutes

if TYPE_CHECKING:
    from pathlib import Path

    from httpx import AsyncClient


@pytest.fixture
def user_routes(client: AsyncClient) -> UserRoutes:
    return UserRoutes(client)


@pytest.fixture
async def uploaded_user(user_routes: UserRoutes, users_dir: Path) -> dict:
    return await user_routes.sign_in_and_upload(users_dir)

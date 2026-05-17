from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers.users import UserRoutes

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.fixture
def user_routes(client: AsyncClient) -> UserRoutes:
    return UserRoutes(client)

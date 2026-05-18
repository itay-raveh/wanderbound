from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.factories import AlbumScenario, sign_in_with_album
from tests.helpers.albums import AlbumRoutes

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture
def album_routes(client: AsyncClient) -> AlbumRoutes:
    return AlbumRoutes(client)


@pytest.fixture
async def signed_album(client: AsyncClient, session: AsyncSession) -> AlbumScenario:
    return await sign_in_with_album(client, session)

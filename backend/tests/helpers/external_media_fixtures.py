from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.factories import AlbumMediaScenario, sign_in_with_album_media
from tests.helpers.external_media import AlbumMediaFactory, ExternalMediaRoutes
from tests.helpers.google_photos import google_connected_album_media

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture
def external_media(client: AsyncClient) -> ExternalMediaRoutes:
    return ExternalMediaRoutes(client)


@pytest.fixture
def album_media_scenario(
    client: AsyncClient, session: AsyncSession
) -> AlbumMediaFactory:
    async def factory(**kwargs: Any) -> AlbumMediaScenario:
        return await sign_in_with_album_media(client, session, **kwargs)

    return factory


@pytest.fixture
def google_album_media_scenario(
    client: AsyncClient, session: AsyncSession
) -> AlbumMediaFactory:
    async def factory(**kwargs: Any) -> AlbumMediaScenario:
        return await google_connected_album_media(client, session, **kwargs)

    return factory

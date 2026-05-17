from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers.google_photos import GooglePhotosRoutes

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.fixture
def google_photos_routes(client: AsyncClient) -> GooglePhotosRoutes:
    return GooglePhotosRoutes(client)

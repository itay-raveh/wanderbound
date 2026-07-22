from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest
    from httpx import AsyncClient

from app.core.config import PublicSettings, get_settings


async def test_public_config_filters_backend_settings(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = "must-not-cross-the-public-config-boundary"
    monkeypatch.setattr(get_settings(), "SECRET_KEY", sentinel)

    response = await client.get("/api/v1/config")

    assert set(response.json()) == set(PublicSettings.model_fields)
    assert "SECRET_KEY" not in response.text
    assert sentinel not in response.text
    assert response.headers["cache-control"] == "no-store"

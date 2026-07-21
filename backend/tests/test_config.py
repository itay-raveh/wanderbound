from typing import TYPE_CHECKING

from fastapi import Response

if TYPE_CHECKING:
    import pytest
    from httpx import AsyncClient

from app import main
from app.core.config import PublicSettings, get_settings


async def test_public_config_is_available(client: AsyncClient) -> None:
    response = await client.get("/api/v1/config")

    assert response.status_code == 200


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


def test_public_config_constructs_a_public_settings_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "must-not-cross-the-public-config-boundary"
    monkeypatch.setattr(get_settings(), "SECRET_KEY", sentinel)

    public_settings = main.public_config(Response())

    assert type(public_settings) is PublicSettings
    assert set(public_settings.model_dump()) == set(PublicSettings.model_fields)
    assert sentinel not in public_settings.model_dump_json()

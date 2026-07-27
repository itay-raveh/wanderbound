from typing import TYPE_CHECKING

from pydantic import AnyHttpUrl

if TYPE_CHECKING:
    import pytest
    from httpx import AsyncClient

from app.core.config import PublicSettings, Settings, get_settings


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


def test_local_login_is_enabled_only_without_providers() -> None:
    assert PublicSettings().local_login_enabled is True
    assert PublicSettings(GOOGLE_CLIENT_ID="google").local_login_enabled is False
    assert PublicSettings(MICROSOFT_CLIENT_ID="microsoft").local_login_enabled is False


def test_production_does_not_require_an_auth_provider() -> None:
    settings = Settings.model_construct(
        ENVIRONMENT="production",
        PUBLIC_URL=AnyHttpUrl("https://wanderbound.example"),
        MAPBOX_TOKEN="mapbox",  # noqa: S106
        GOOGLE_CLIENT_ID="",
        MICROSOFT_CLIENT_ID="",
        GOOGLE_CLIENT_SECRET="",
    )

    assert settings._require_in_production() is settings  # ty: ignore[call-non-callable]

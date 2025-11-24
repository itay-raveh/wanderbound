"""Application settings using Pydantic."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Debug mode (set via DEBUG environment variable)
    debug: bool = False

    # API URLs
    flag_cdn_base_url: str = "https://flagcdn.com/w40"
    opentopodata_api_url: str = "https://api.opentopodata.org/v1/aster30m"
    natural_earth_geojson_url: str = (
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
        "ne_50m_admin_0_countries.geojson"
    )
    mapsicon_base_url: str = (
        "https://raw.githubusercontent.com/djaiss/mapsicon/master/all"
    )
    weather_icon_base_url: str = (
        "https://basmilius.github.io/weather-icons/production/fill/all"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

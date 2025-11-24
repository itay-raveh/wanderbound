"""Application settings using Pydantic."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Debug mode (set via DEBUG environment variable)
    debug: bool = False

    # API URL templates (use .format() with placeholders)
    flag_cdn_url: str = "https://flagcdn.com/w40/{country_code}.png"
    opentopodata_api_url: str = (
        "https://api.opentopodata.org/v1/aster30m?locations={locations}"
    )
    natural_earth_geojson_url: str = (
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
        "ne_50m_admin_0_countries.geojson"
    )
    mapsicon_url: str = (
        "https://raw.githubusercontent.com/djaiss/mapsicon/master/all/{country_code}/vector.svg"
    )
    weather_icon_url: str = (
        "https://basmilius.github.io/weather-icons/production/fill/all/{icon_name}.svg"
    )
    visual_crossing_api_url: str = (
        "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
        "{location}/{date}?key={key}&unitGroup=metric&include=hours&elements={elements}"
    )

    # Weather API key (optional - set via VISUAL_CROSSING_API_KEY environment variable)
    # Get a free key at https://www.visualcrossing.com/weather-api
    visual_crossing_api_key: str | None = None

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

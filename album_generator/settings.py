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

    # Color constants
    default_accent_color: str = "#ff69b4"  # Hot pink fallback color

    # Color extraction thresholds
    brightness_threshold_high: int = 240  # Filter out very bright colors (near white)
    brightness_threshold_low: int = 15  # Filter out very dark colors (near black)
    color_count_min_ratio: float = (
        0.3  # Minimum ratio for color to be considered prominent
    )
    color_conflict_threshold: float = 0.10  # Minimum color distance to avoid conflicts

    # Color adjustment constants
    light_mode_target_brightness: float = 0.55
    dark_mode_target_brightness: float = 0.45
    max_blend_factor: float = 0.25  # Maximum blending factor for color adjustment

    # Description layout thresholds
    description_three_columns_threshold: int = 2000  # Characters
    description_two_columns_threshold: int = 500  # Characters

    # Weather temperature thresholds
    feels_like_display_threshold: float = (
        3.0  # Only show "feels like" if difference >= 3°C
    )
    temperature_mismatch_threshold: float = (
        10.0  # Warn if API and trip data differ by > 10°C
    )

    # Photo layout thresholds
    description_max_char_cover_photo: int = (
        800  # Max description length to use cover photo
    )
    min_photo_size_percent: float = (
        15.0  # Minimum percentage of page area each photo should occupy
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

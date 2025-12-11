"""Application settings using Pydantic."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Debug mode (set via DEBUG environment variable)
    debug: bool = Field(default=False)
    cache_dir: Path = Path(__file__).parents[2] / ".psagen_cache"

    flag_cdn_url: str = "https://flagcdn.com/w40/{country_code}.png"
    opentopodata_api_url: str = "https://api.opentopodata.org/v1/aster30m?locations={locations}"
    natural_earth_geojson_url: str = (
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
    )
    weather_icon_url: str = (
        "https://basmilius.github.io/weather-icons/production/fill/all/{icon_name}.svg"
    )
    visual_crossing_api_url: str = (
        "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
        "{lat},{lon}/{date}?key={key}&unitGroup=metric&include=hours&elements=datetime,tempmax,tempmin,feelslikemax,feelslikemin,icon"
    )
    # Get a free key at https://www.visualcrossing.com/weather-api
    visual_crossing_api_key: str

    accent_color: str = Field(default="#ff4d6d", pattern=r"^#[0-9a-fA-F]{6}$")
    map_fill_color: str = Field(default="#e0e0e0", pattern=r"^#[0-9a-fA-F]{6}$")

    description_three_columns_threshold: int = Field(default=2000, gt=0)
    description_two_columns_threshold: int = Field(default=500, gt=0)

    feels_like_display_threshold: float = Field(default=3.0, ge=0.0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()

"""Application settings using Pydantic."""

import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Debug mode (set via DEBUG environment variable)
    debug: bool = Field(default=False)

    @property
    def root_dir(self) -> Path:
        """Return the project root directory, handling frozen (executable) state."""
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent

        return Path(__file__).parents[2]

    @property
    def cache_dir(self) -> Path:
        return self.root_dir / ".psagen_cache"

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

    light_mode: bool = False

    long_description_threshold: int = Field(default=1000, gt=0)
    extra_long_description_threshold: int = Field(default=4350, gt=0)

    feels_like_display_threshold: float = Field(default=3.0, ge=0.0)

    model_config = SettingsConfigDict(
        # We can't use self.root_dir here because model_config is evaluated at class definition time
        # So we duplicate the logic slightly or use a computed field workaround if strictly needed.
        # But BaseSettings handles paths relative to CWD mostly.
        # For safety in frozen apps, we compute it dynamically.
        env_file=(
            Path(sys.executable).parent / ".env" if getattr(sys, "frozen", False) else ".env"
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# noinspection PyArgumentList
settings = Settings()  # ty:ignore[missing-argument]  # pyright: ignore[reportCallIssue]

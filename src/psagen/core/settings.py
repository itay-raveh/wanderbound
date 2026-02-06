"""Application settings using Pydantic."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    debug: bool = Field(default=False)

    @property
    def root_dir(self) -> Path:
        """Return the project root directory."""
        return Path(__file__).parents[3]

    @property
    def static_dir(self) -> Path:
        """Return the static directory path."""
        return self.root_dir / "src" / "psagen" / "static"

    data_dir: Path = Field(default_factory=Path.cwd)

    @property
    def cache_dir(self) -> Path:
        """Return the cache directory path."""
        # TODO(itay): move to data_dir
        return self.root_dir / ".psagen_cache"

    # External API URLs
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
    visual_crossing_api_key: str = ""  # Optional: get free key at visualcrossing.com

    # Display settings
    light_mode: bool = False
    long_description_threshold: int = Field(default=1000, gt=0)
    extra_long_description_threshold: int = Field(default=4350, gt=0)
    feels_like_display_threshold: float = Field(default=3.0, ge=0.0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()

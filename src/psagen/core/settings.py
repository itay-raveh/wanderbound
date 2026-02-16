"""Application settings using Pydantic."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    storage_secret: str

    project_root_dir: Path = Path(__file__).parent.parent

    @property
    def static_dir(self) -> Path:
        return self.project_root_dir / "static"

    data_dir: Path = Field(default_factory=Path.cwd)

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def users_dir(self) -> Path:
        return self.data_dir / "users"

    # External API URLs
    flag_cdn_url: str = "https://flagcdn.com/w80/{country_code}.png"
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

    visual_crossing_api_key: str | None

    # Display settings
    long_description_threshold: int = Field(default=1000, gt=0)
    extra_long_description_threshold: int = Field(default=4350, gt=0)
    feels_like_display_threshold: float = Field(default=3.0, ge=0.0)

    model_config = SettingsConfigDict(
        env_prefix="PSAGEN_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# noinspection PyArgumentList
settings = Settings()  # pyright: ignore[reportCallIssue]

"""Application settings using Pydantic."""

from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PDFSettings(BaseModel):
    viewport_width: int = Field(default=1123, gt=0)
    viewport_height: int = Field(default=794, gt=0)


class PhotoSettings(BaseModel):
    # Aspect ratio matching
    aspect_ratio_tolerance: float = Field(default=0.1, gt=0.0)

    # Layout constants


class ProgressSettings(BaseModel):
    min_position: float = 1.0
    max_position: float = 99.0
    box_min_position: float = 6.0
    box_max_position: float = 95.0


class FileSettings(BaseModel):
    # File names
    album_html_file: str = "album.html"
    album_pdf_file: str = "album.pdf"

    # Directory names
    assets_dir: str = "assets"
    images_dir: str = "images"
    static_dir: str = "static"
    cache_dir: Path = Path(".cache")  #  Path.home() / ".cache" / "polarsteps-album-generator"


class MapSettings(BaseModel):
    default_fill_color: str = Field(default="#e0e0e0", pattern=r"^#[0-9a-fA-F]{6}$")


class Settings(BaseSettings):
    # Debug mode (set via DEBUG environment variable)
    debug: bool = Field(default=False)

    # API URL templates (use .format() with placeholders)
    flag_cdn_url: str = "https://flagcdn.com/w40/{country_code}.png"
    opentopodata_api_url: str = "https://api.opentopodata.org/v1/aster30m?locations={locations}"
    natural_earth_geojson_url: str = (
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
        "ne_50m_admin_0_countries.geojson"
    )
    weather_icon_url: str = (
        "https://basmilius.github.io/weather-icons/production/fill/all/{icon_name}.svg"
    )
    visual_crossing_api_url: str = (
        "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
        "{location}/{date}?key={key}&unitGroup=metric&include=hours&elements={elements}"
    )

    # Get a free key at https://www.visualcrossing.com/weather-api
    visual_crossing_api_key: str = Field(..., pattern=r"^[a-zA-Z0-9]{32}$")

    # Color constants
    default_accent_color: str = Field(default="#ff69b4", pattern=r"^#[0-9a-fA-F]{6}$")

    # Color extraction thresholds
    brightness_threshold_high: int = Field(default=240, ge=0, le=255)
    brightness_threshold_low: int = Field(default=15, ge=0, le=255)
    color_count_min_ratio: float = Field(default=0.3, ge=0.0, le=1.0)
    color_conflict_threshold: float = Field(default=0.10, ge=0.0, le=1.0)

    # Color adjustment constants
    light_mode_target_brightness: float = Field(default=0.55, ge=0.0, le=1.0)
    dark_mode_target_brightness: float = Field(default=0.45, ge=0.0, le=1.0)
    max_blend_factor: float = Field(default=0.25, ge=0.0, le=1.0)

    # Description layout thresholds
    description_three_columns_threshold: int = Field(default=2000, gt=0)
    description_two_columns_threshold: int = Field(default=500, gt=0)

    # Weather temperature thresholds
    feels_like_display_threshold: float = Field(default=3.0, ge=0.0)
    temperature_mismatch_threshold: float = Field(default=10.0, ge=0.0)

    # Photo layout thresholds
    description_max_char_cover_photo: int = Field(default=800, gt=0)

    # Sub-models for organized constants
    pdf: PDFSettings = PDFSettings()
    photo: PhotoSettings = PhotoSettings()
    progress: ProgressSettings = ProgressSettings()
    file: FileSettings = FileSettings()
    map: MapSettings = MapSettings()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_brightness_thresholds(self) -> "Settings":
        if self.brightness_threshold_high <= self.brightness_threshold_low:
            raise ValueError(
                "brightness_threshold_high must be greater than brightness_threshold_low"
            )
        return self


settings = Settings()

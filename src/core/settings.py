"""Application settings using Pydantic."""

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions import ConfigurationError


class PDFSettings(BaseModel):
    """PDF generation settings."""

    viewport_width: int = 1123
    viewport_height: int = 794


class PhotoSettings(BaseModel):
    """Photo selection and layout settings."""

    # Aspect ratio matching
    aspect_ratio_tolerance: float = 0.1
    ideal_cover_aspect_ratio: float = 4 / 5  # 4:5 portrait
    uniform_aspect_ratio_tolerance: float = 0.05

    # Layout constants
    max_photos_to_test: int = 9
    photo_count_for_special_layouts: int = 3
    multi_row_layout_counts: tuple[int, ...] = (5, 6)

    # Scoring constants
    score_three_portraits_bonus: float = 100.0
    score_portrait_first_bonus: float = 10.0
    score_layout_bonus_three_portraits: float = 15000.0
    score_uniform_aspect_ratio_bonus: float = 2000.0
    score_portrait_landscape_split_bonus: float = 5000.0
    score_photo_count_multiplier: float = 10000.0

    # Photo area calculation
    photo_area_full_page: float = 100.0
    photo_area_portrait_left: float = 50.0
    photo_area_landscape_right: float = 25.0

    @property
    def photo_area_three_portraits(self) -> float:
        """Calculate three portraits area."""
        return self.photo_area_full_page / 3


class ProgressSettings(BaseModel):
    """Progress bar positioning settings."""

    min_position: float = 1.0
    max_position: float = 99.0
    box_min_position: float = 6.0
    box_max_position: float = 95.0


class FileSettings(BaseModel):
    """File and directory name settings."""

    # File names
    album_html_file: str = "album.html"
    album_pdf_file: str = "album.pdf"
    font_file: str = "Renner.ttf"

    # Directory names
    assets_dir: str = "assets"
    images_dir: str = "images"
    fonts_dir: str = "fonts"
    css_dir: str = "css"
    static_dir: str = "static"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Debug mode (set via DEBUG environment variable)
    debug: bool = False

    # API URL templates (use .format() with placeholders)
    flag_cdn_url: str = "https://flagcdn.com/w40/{country_code}.png"
    opentopodata_api_url: str = "https://api.opentopodata.org/v1/aster30m?locations={locations}"
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
    color_count_min_ratio: float = 0.3  # Minimum ratio for color to be considered prominent
    color_conflict_threshold: float = 0.10  # Minimum color distance to avoid conflicts

    # Color adjustment constants
    light_mode_target_brightness: float = 0.55
    dark_mode_target_brightness: float = 0.45
    max_blend_factor: float = 0.25  # Maximum blending factor for color adjustment

    # Description layout thresholds
    description_three_columns_threshold: int = 2000  # Characters
    description_two_columns_threshold: int = 500  # Characters

    # Weather temperature thresholds
    feels_like_display_threshold: float = 3.0  # Only show "feels like" if difference >= 3°C
    temperature_mismatch_threshold: float = 10.0  # Warn if API and trip data differ by > 10°C

    # Photo layout thresholds
    description_max_char_cover_photo: int = 800  # Max description length to use cover photo
    min_photo_size_percent: float = 15.0  # Minimum percentage of page area each photo should occupy

    # Sub-models for organized constants
    pdf: PDFSettings = PDFSettings()
    photo: PhotoSettings = PhotoSettings()
    progress: ProgressSettings = ProgressSettings()
    file: FileSettings = FileSettings()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Module-level settings instance
# Python modules are singletons, so this ensures only one Settings instance
try:
    settings = Settings()
except Exception as e:
    raise ConfigurationError(
        f"Failed to load application settings: {e}. "
        f"Please check your .env file and environment variables."
    ) from e

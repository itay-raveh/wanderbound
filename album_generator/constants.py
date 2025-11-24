"""Constants used throughout the album generator."""

# Color constants
DEFAULT_ACCENT_COLOR = "#ff69b4"  # Hot pink fallback color

# Color extraction thresholds
BRIGHTNESS_THRESHOLD_HIGH = 240  # Filter out very bright colors (near white)
BRIGHTNESS_THRESHOLD_LOW = 15  # Filter out very dark colors (near black)
COLOR_COUNT_MIN_RATIO = 0.3  # Minimum ratio for color to be considered prominent
COLOR_CONFLICT_THRESHOLD = 0.10  # Minimum color distance to avoid conflicts

# Color adjustment constants
LIGHT_MODE_TARGET_BRIGHTNESS = 0.55
DARK_MODE_TARGET_BRIGHTNESS = 0.45
MAX_BLEND_FACTOR = 0.25  # Maximum blending factor for color adjustment

# Description layout thresholds
DESCRIPTION_THREE_COLUMNS_THRESHOLD = 2000  # Characters
DESCRIPTION_TWO_COLUMNS_THRESHOLD = 500  # Characters

# Weather temperature thresholds
FEELS_LIKE_DISPLAY_THRESHOLD = 3.0  # Only show "feels like" if difference >= 3°C
TEMPERATURE_MISMATCH_THRESHOLD = 1.0  # Warn if API and trip data differ by > 1°C

# Photo layout thresholds
DESCRIPTION_MAX_CHAR_COVER_PHOTO = 800  # Max description length to use cover photo
MIN_PHOTO_SIZE_PERCENT = (
    15.0  # Minimum percentage of page area each photo should occupy
)

# Note: API URLs and DEBUG setting have been moved to settings.py (Pydantic settings)
# These constants remain for backward compatibility but should use settings.get_settings() instead

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

# Weather icon provider (using basmilius weather-icons - colorful, elegant, with proper sun design)
# Uses semantic names matching weather conditions (e.g., clear-day, partly-cloudy-day)
WEATHER_ICON_BASE_URL = "https://basmilius.github.io/weather-icons/production/fill/all"

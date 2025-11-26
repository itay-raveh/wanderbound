"""Weather condition formatting functions."""

from functools import lru_cache

__all__ = ["format_weather_condition"]


@lru_cache(maxsize=128)
def format_weather_condition(condition: str | None) -> str:
    """Format weather condition code to display text.

    Args:
        condition: Weather condition code (e.g., 'clear-day', 'rain')

    Returns:
        Formatted weather condition string in uppercase
    """
    if not condition:
        return "UNKNOWN"

    condition_map = {
        "clear-day": "CLEAR",
        "clear-night": "CLEAR",
        "rain": "RAIN",
        "snow": "SNOW",
        "sleet": "SLEET",
        "wind": "WIND",
        "fog": "FOG",
        "cloudy": "CLOUDY",
        "partly-cloudy-day": "PARTLY CLOUDY",
        "partly-cloudy-night": "PARTLY CLOUDY",
    }

    return condition_map.get(condition, condition.upper().replace("-", " "))

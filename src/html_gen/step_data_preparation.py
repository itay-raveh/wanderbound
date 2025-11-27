"""Step data preparation for HTML generation."""

from typing import Any

from langdetect import LangDetectException, detect

from src.apis import format_altitude
from src.apis.weather import WeatherData
from src.formatters import format_coordinates, format_date, format_weather_condition
from src.logger import get_logger
from src.models import Step, TripData
from src.settings import settings
from src.type_definitions import StepContext, StepData, StepExternalData
from src.utils.dates import calculate_day_number

logger = get_logger(__name__)

__all__ = [
    "_calculate_progress",
    "_calculate_progress_positions",
    "_clean_description",
    "_extract_map_data",
    "_extract_weather_icons",
    "_format_temperature",
    "_is_hebrew",
    "_split_description",
    "prepare_step_data",
]


def _is_hebrew(text: str) -> bool:
    """Check if text is Hebrew using fast Unicode check first, then langdetect if needed.

    Args:
        text: Text to check

    Returns:
        True if text is Hebrew, False otherwise
    """
    if not text or not text.strip():
        return False

    # Fast Unicode range check first (instant, no network)
    has_hebrew_chars = any("\u0590" <= char <= "\u05ff" for char in text)
    # If we found Hebrew characters, it's likely Hebrew text
    # Only use langdetect for very short texts that might be ambiguous
    if has_hebrew_chars and len(text.strip()) > 10:
        return True

    # Use langdetect for mixed content or short texts
    try:
        detected_lang: str = str(detect(text))
    except LangDetectException:
        # Fallback to Unicode check if langdetect fails
        return has_hebrew_chars
    else:
        return detected_lang == "he"


def _split_description(
    description: str, *, _is_hebrew: bool, _use_three_columns: bool = False
) -> tuple[str, str, str]:
    """Split description into columns. Returns full text for CSS column handling.

    The CSS handles the actual column layout, so we return the full cleaned text
    in the first column and empty strings for the others.

    Args:
        description: Description text to split
        _is_hebrew: Whether the text is Hebrew (currently unused - CSS handles layout)
        _use_three_columns: Whether to use three columns (currently unused - CSS handles layout)

    Returns:
        Tuple of (col1, col2, col3) text where col1 contains the full cleaned text
    """
    if not description:
        return ("", "", "")

    parts = description.split("\n\n")
    paragraphs = []
    for p in parts:
        cleaned = p.strip()
        if cleaned:
            paragraphs.append(cleaned)
        elif paragraphs and paragraphs[-1]:
            paragraphs.append("")

    if not paragraphs:
        return ("", "", "")

    full_text = "\n\n".join(paragraphs).strip().lstrip()
    return (full_text, "", "")


def _clean_description(description: str) -> str:
    """Clean and normalize step description text.

    Args:
        description: Raw description text

    Returns:
        Cleaned description with normalized whitespace
    """
    if not description:
        return ""

    description = description.lstrip()
    lines = description.split("\n")
    cleaned_lines = []
    for line in lines:
        cleaned = line.lstrip()
        if cleaned:
            cleaned_lines.append(cleaned)
        elif cleaned_lines and cleaned_lines[-1]:
            cleaned_lines.append("")
    return "\n".join(cleaned_lines).strip().lstrip()


def _format_temperature(temp: float | None, feels_like: float | None) -> str:
    """Format temperature string with feels like if meaningfully different.

    Only shows "feels like" if the difference is >= 3°C, as smaller differences
    are not meaningful to users.

    Args:
        temp: Actual temperature in Celsius
        feels_like: "Feels like" temperature in Celsius

    Returns:
        Formatted temperature string (e.g., "25°" or "25° (28°)" or "N/A")
    """
    if temp is None:
        return "N/A"
    # Only show feels like if difference is meaningful
    # Using module-level settings
    if feels_like is not None and abs(feels_like - temp) >= settings.feels_like_display_threshold:
        return f"{int(temp)}° ({int(feels_like)}°)"
    return f"{int(temp)}°"


def _calculate_progress(
    step: Step,
    step_index: int,
    steps: list[Step],
    trip_data: TripData,
    *,
    use_step_range: bool,
) -> tuple[int, float]:
    """Calculate day number and progress percentage for a step.

    Args:
        step: Step to calculate progress for
        step_index: Zero-based index of step in steps list
        steps: Complete list of all steps
        trip_data: Trip metadata
        use_step_range: If True, use step range (1 to len(steps)); if False, use trip days

    Returns:
        Tuple of (day_num, progress_percent)
    """
    if use_step_range:
        day_num = step_index + 1
        progress_percent = (day_num / len(steps)) * 100 if steps else 0
    elif trip_data.start_date is None:
        progress_percent = 0
        day_num = 1
    else:
        day_num = calculate_day_number(step.start_time, trip_data.start_date, trip_data.timezone_id)
        if trip_data.end_date is not None:
            total_days = calculate_day_number(
                trip_data.end_date, trip_data.start_date, trip_data.timezone_id
            )
            progress_percent = (day_num / total_days) * 100 if total_days > 0 else 0
        else:
            progress_percent = 0

    return day_num, progress_percent


def _calculate_progress_positions(progress_percent: float) -> tuple[float, float]:
    """Calculate arrow and box positions for progress bar.

    Args:
        progress_percent: Progress percentage (0-100)

    Returns:
        Tuple of (box_center_position, arrow_bar_position)
    """
    # Using module-level settings
    arrow_bar_position = max(
        settings.progress.min_position, min(settings.progress.max_position, progress_percent)
    )
    if progress_percent < settings.progress.box_min_position:
        box_center_position = settings.progress.box_min_position
    elif progress_percent > settings.progress.box_max_position:
        box_center_position = settings.progress.box_max_position
    else:
        box_center_position = progress_percent
    return box_center_position, arrow_bar_position


def _extract_map_data(
    map_data: tuple[str | None, str | None, tuple[float, float] | None] | None,
) -> tuple[str | None, str | None, float | None, float | None]:
    """Extract map data components.

    Args:
        map_data: Map data tuple or None

    Returns:
        Tuple of (country_map_data_uri, country_map_svg, map_dot_x, map_dot_y)
    """
    if map_data and isinstance(map_data, tuple) and len(map_data) == 3:
        country_map_data_uri, country_map_svg, dot_pos = map_data
        map_dot_x, map_dot_y = dot_pos if dot_pos else (None, None)
        return country_map_data_uri, country_map_svg, map_dot_x, map_dot_y
    return None, None, None, None


def _extract_weather_icons(
    weather_data: WeatherData, step: Step, settings: Any
) -> tuple[str | None, str | None]:
    """Extract and generate weather icon URLs.

    Args:
        weather_data: WeatherData object
        step: Step object
        settings: Settings object

    Returns:
        Tuple of (day_weather_icon_url, night_weather_icon_url)
    """
    day_icon_api = weather_data.day_icon
    night_icon = weather_data.night_icon

    day_icon_name = day_icon_api
    if not day_icon_name and step.weather_condition:
        day_icon_name = step.weather_condition.lower().replace("_", "-")

    day_weather_icon_url = (
        settings.weather_icon_url.format(icon_name=day_icon_name) if day_icon_name else None
    )
    night_weather_icon_url = (
        settings.weather_icon_url.format(icon_name=night_icon) if night_icon else None
    )
    return day_weather_icon_url, night_weather_icon_url


def prepare_step_data(
    context: StepContext,
    external_data: StepExternalData,
    *,
    use_step_range: bool,
    light_mode: bool = False,
) -> StepData:
    """Prepare all data needed for rendering a step in the HTML template.

    Args:
        context: Dictionary containing step, step_index, steps, and trip_data
        external_data: Dictionary containing elevation, weather_data, flag_data,
            map_data, and cover_image_path
        use_step_range: If True, calculate progress based on step range; if False, use trip days
        light_mode: If True, use light mode color scheme; if False, use dark mode

    Returns:
        Dictionary containing all template variables for rendering this step
    """
    step = context["step"]
    step_index = context["step_index"]
    steps = context["steps"]
    trip_data = context["trip_data"]

    elevation = external_data.get("elevation")
    weather_data_raw = external_data.get("weather_data")
    weather_data = weather_data_raw if isinstance(weather_data_raw, WeatherData) else WeatherData()
    flag_data = external_data.get("flag_data")
    map_data = external_data.get("map_data")
    cover_image_path = external_data.get("cover_image_path")

    description = _clean_description(step.description or "")

    is_hebrew = _is_hebrew(description)
    # Using module-level settings
    use_three_columns = len(description) > settings.description_three_columns_threshold
    use_two_columns = (
        len(description) > settings.description_two_columns_threshold or use_three_columns
    )

    desc_col1, _desc_col2, _desc_col3 = _split_description(
        description, _is_hebrew=is_hebrew, _use_three_columns=use_three_columns
    )

    day_num, progress_percent = _calculate_progress(
        step, step_index, steps, trip_data, use_step_range=use_step_range
    )

    box_center_position, arrow_bar_position = _calculate_progress_positions(progress_percent)

    country_map_data_uri, country_map_svg, map_dot_x, map_dot_y = _extract_map_data(map_data)

    date_data = format_date(step.start_time, step.timezone_id)
    coords_data = format_coordinates(step.location.lat, step.location.lon)

    day_temp_api = weather_data.day_temp
    night_temp = weather_data.night_temp
    day_feels_like = weather_data.day_feels_like
    night_feels_like = weather_data.night_feels_like

    # Using module-level settings
    if day_temp_api is not None and step.weather_temperature is not None:
        temp_diff = abs(day_temp_api - step.weather_temperature)
        if temp_diff > settings.temperature_mismatch_threshold:
            logger.warning(
                "Temperature mismatch for %s on %s %s: API reports %.1f°C, "
                "trip data has %.1f°C (difference: %.1f°C). Using API data.",
                step.city,
                date_data["month"],
                date_data["day"],
                day_temp_api,
                step.weather_temperature,
                temp_diff,
            )

    day_weather_icon_url, night_weather_icon_url = _extract_weather_icons(
        weather_data, step, settings
    )

    country_flag_data_uri, accent_color = flag_data if flag_data else (None, None)

    day_temp_display = day_temp_api
    temp_str = _format_temperature(day_temp_display, day_feels_like)
    temp_night_str = _format_temperature(night_temp, night_feels_like)

    return {
        "city": step.city,
        "country": step.country,
        "country_code": step.country_code,
        "coords_lat": coords_data["lat"],
        "coords_lon": coords_data["lon"],
        "date_month": date_data["month"],
        "date_day": date_data["day"],
        "weather": format_weather_condition(step.weather_condition),
        "day_weather_icon_url": day_weather_icon_url,
        "night_weather_icon_url": night_weather_icon_url,
        "temp_str": temp_str,
        "temp_night_str": temp_night_str,
        "altitude_str": format_altitude(elevation),
        "day_num": day_num,
        "progress_percent": progress_percent,
        "day_counter_box_position": box_center_position,
        "day_counter_arrow_position": arrow_bar_position,
        "cover_image_path": cover_image_path,
        "country_flag_data_uri": country_flag_data_uri,
        "country_map_data_uri": country_map_data_uri,
        "country_map_svg": country_map_svg,
        "map_dot_x": map_dot_x,
        "map_dot_y": map_dot_y,
        "accent_color": accent_color,
        "description": description if not use_two_columns else None,
        "description_full": desc_col1.lstrip() if use_two_columns and desc_col1 else "",
        "desc_dir": "rtl" if is_hebrew else "ltr",
        "desc_align": "right" if is_hebrew else "left",
        "use_two_columns": use_two_columns,
        "use_three_columns": use_three_columns,
        "light_mode": light_mode,
    }

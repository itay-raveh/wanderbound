"""Step data preparation for HTML generation."""

from langdetect import LangDetectException, detect

from ..apis import format_altitude
from ..apis.weather import WeatherData
from ..formatters import format_coordinates, format_date, format_weather_condition
from ..logger import get_logger
from ..models import Photo, Step, TripData
from ..settings import get_settings
from ..types import StepData
from ..utils.dates import calculate_day_number

logger = get_logger(__name__)

__all__ = [
    "_is_hebrew",
    "_split_description",
    "_clean_description",
    "_format_temperature",
    "_calculate_progress",
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
        return detected_lang == "he"
    except (LangDetectException, Exception):
        # Fallback to Unicode check if langdetect fails
        return has_hebrew_chars


def _split_description(
    description: str, is_hebrew: bool, use_three_columns: bool = False
) -> tuple[str, str, str]:
    """Split description into columns. Returns full text for CSS column handling.

    The CSS handles the actual column layout, so we return the full cleaned text
    in the first column and empty strings for the others.

    Args:
        description: Description text to split
        is_hebrew: Whether the text is Hebrew (affects splitting logic)
        use_three_columns: Whether to use three columns

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
    settings = get_settings()
    if feels_like is not None and abs(feels_like - temp) >= settings.feels_like_display_threshold:
        return f"{int(temp)}° ({int(feels_like)}°)"
    return f"{int(temp)}°"


def _calculate_progress(
    step: Step,
    step_index: int,
    steps: list[Step],
    trip_data: TripData,
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
    else:
        if trip_data.start_date is None:
            progress_percent = 0
            day_num = 1
        else:
            day_num = calculate_day_number(
                step.start_time, trip_data.start_date, trip_data.timezone_id
            )
            if trip_data.end_date is not None:
                total_days = calculate_day_number(
                    trip_data.end_date, trip_data.start_date, trip_data.timezone_id
                )
                progress_percent = (day_num / total_days) * 100 if total_days > 0 else 0
            else:
                progress_percent = 0

    return day_num, progress_percent


def prepare_step_data(
    step: Step,
    cover_photo: Photo | None,
    step_index: int,
    steps: list[Step],
    trip_data: TripData,
    use_step_range: bool,
    elevation: float | None,
    weather_data: WeatherData,
    flag_data: tuple[str | None, str | None] | None,
    map_data: tuple[str | None, str | None, tuple[float, float] | None] | None,
    cover_image_path: str | None,
    light_mode: bool = False,
) -> StepData:
    """Prepare all data needed for rendering a step in the HTML template.

    Args:
        step: The step to prepare data for
        cover_photo: Cover Photo object for this step, or None if no cover photo
        step_index: Zero-based index of this step in the steps list
        steps: Complete list of all steps being rendered
        trip_data: Trip metadata including start/end dates and timezone
        use_step_range: If True, calculate progress based on step range; if False, use trip days
        elevation: Altitude in meters for this step's location, or None if unavailable
        weather_data: WeatherData object containing temperatures, feels like temperatures, and icons
        flag_data: Tuple of (country_flag_data_uri, accent_color) or None
        map_data: Tuple of (country_map_data_uri, country_map_svg, (map_dot_x, map_dot_y)) or None
        cover_image_path: Relative path to cover image file or None
        light_mode: If True, use light mode color scheme; if False, use dark mode

    Returns:
        Dictionary containing all template variables for rendering this step
    """
    description = _clean_description(step.description or "")

    is_hebrew = _is_hebrew(description)
    settings = get_settings()
    use_three_columns = len(description) > settings.description_three_columns_threshold
    use_two_columns = (
        len(description) > settings.description_two_columns_threshold or use_three_columns
    )

    desc_col1, desc_col2, desc_col3 = _split_description(description, is_hebrew, use_three_columns)

    day_num, progress_percent = _calculate_progress(
        step, step_index, steps, trip_data, use_step_range
    )

    settings = get_settings()
    arrow_bar_position = max(
        settings.progress.min_position, min(settings.progress.max_position, progress_percent)
    )
    # For very low progress (first day), position box at a safe minimum
    # The translateX(-55%) moves it left by 55% of its width, so we need enough margin
    # Estimate box width ~60px, container ~400px, so need ~6% minimum to avoid going negative
    # For high progress (final day), cap at 95% to ensure box doesn't go off right edge
    if progress_percent < settings.progress.box_min_position:
        box_center_position = settings.progress.box_min_position
    elif progress_percent > settings.progress.box_max_position:
        box_center_position = settings.progress.box_max_position
    else:
        box_center_position = progress_percent

    # Extract map data (already fetched in batch)
    map_dot_x, map_dot_y = None, None
    country_map_data_uri = None
    country_map_svg = None
    if map_data and isinstance(map_data, tuple) and len(map_data) == 3:
        country_map_data_uri, country_map_svg, dot_pos = map_data
        if dot_pos:
            map_dot_x, map_dot_y = dot_pos
    else:
        country_map_data_uri, country_map_svg, dot_pos = None, None, None

    # Extract weather data (already fetched in batch)
    day_temp_api = weather_data.day_temp
    night_temp = weather_data.night_temp
    day_feels_like = weather_data.day_feels_like
    night_feels_like = weather_data.night_feels_like
    day_icon_api = weather_data.day_icon
    night_icon = weather_data.night_icon

    date_data = format_date(step.start_time, step.timezone_id)
    coords_data = format_coordinates(step.location.lat, step.location.lon)

    # Compare API day temperature with trip data temperature (for logging only)
    # Always use API data as it's more accurate
    if day_temp_api is not None and step.weather_temperature is not None:
        temp_diff = abs(day_temp_api - step.weather_temperature)
        if temp_diff > settings.temperature_mismatch_threshold:
            logger.warning(
                f"Temperature mismatch for {step.city} on {date_data['month']} {date_data['day']}: "
                f"API reports {day_temp_api:.1f}°C, trip data has {step.weather_temperature:.1f}°C "
                f"(difference: {temp_diff:.1f}°C). Using API data."
            )

    # Always use API day icon if available, otherwise fall back to trip data weather condition
    day_icon_name = day_icon_api
    if not day_icon_name and step.weather_condition:
        day_icon_name = step.weather_condition.lower().replace("_", "-")

    # Generate icon URLs
    day_weather_icon_url = (
        settings.weather_icon_url.format(icon_name=day_icon_name) if day_icon_name else None
    )
    night_weather_icon_url = (
        settings.weather_icon_url.format(icon_name=night_icon) if night_icon else None
    )

    # Extract flag data (already fetched in batch)
    country_flag_data_uri = None
    accent_color = None
    if flag_data:
        country_flag_data_uri, accent_color = flag_data

    # Format temperatures with feels like if available
    # Always use API temperature (more accurate)
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
    }

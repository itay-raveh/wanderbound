"""Step data preparation for HTML generation."""

from datetime import datetime
from functools import cache
from zoneinfo import ZoneInfo

from geopy import Point

from src.core.logger import get_logger
from src.core.settings import settings
from src.core.text import is_hebrew
from src.data.models import (
    MapResult,
    Step,
    StepContext,
    StepData,
    StepExternalData,
    TripData,
    WeatherData,
)
from src.services.altitude import format_altitude

logger = get_logger(__name__)


def _clean_description(description: str) -> str:
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


def _calculate_progress(
    step: Step,
    step_index: int,
    steps: list[Step],
    trip_data: TripData,
    *,
    use_step_range: bool,
) -> tuple[int, float]:
    if use_step_range:
        day_num = step_index + 1
        progress_percent = (day_num / len(steps)) * 100 if steps else 0
    else:
        day_num = _calculate_day_number(
            step.start_time, trip_data.start_date, trip_data.timezone_id
        )
        total_days = _calculate_day_number(
            trip_data.end_date, trip_data.start_date, trip_data.timezone_id
        )
        progress_percent = (day_num / total_days) * 100 if total_days > 0 else 0

    return day_num, progress_percent


def _calculate_day_number(
    step_start: float | None, trip_start: float | None, timezone_id: str
) -> int:
    if not step_start or not trip_start:
        return 0

    tz = ZoneInfo(timezone_id)
    step_dt = datetime.fromtimestamp(step_start, tz=tz)
    trip_dt = datetime.fromtimestamp(trip_start, tz=tz)

    delta = step_dt.date() - trip_dt.date()
    return delta.days + 1


def _calculate_progress_positions(progress_percent: float) -> tuple[float, float]:
    # Using module-level settings
    arrow_bar_position = max(
        settings.progress.min_position,
        min(settings.progress.max_position, progress_percent),
    )
    if progress_percent < settings.progress.box_min_position:
        box_center_position = settings.progress.box_min_position
    elif progress_percent > settings.progress.box_max_position:
        box_center_position = settings.progress.box_max_position
    else:
        box_center_position = progress_percent
    return box_center_position, arrow_bar_position


def _extract_map_data(
    map_result: MapResult | None,
) -> tuple[str | None, float | None, float | None]:
    if map_result:
        map_dot_x, map_dot_y = map_result.dot_position if map_result.dot_position else (None, None)
        return map_result.svg_content, map_dot_x, map_dot_y
    return None, None, None


def _extract_weather_icons(weather_data: WeatherData, step: Step) -> tuple[str | None, str | None]:
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
    step = context.step
    step_index = context.step_index
    steps = context.steps
    trip_data = context.trip_data

    elevation = external_data.elevation

    weather_result = external_data.weather_data
    weather_data = weather_result.data if weather_result and weather_result.data else WeatherData()

    flag_result = external_data.flag_data
    map_result = external_data.map_data
    cover_image_path = external_data.cover_image_path

    description = _clean_description(step.description or "")

    is_hebrew_text = is_hebrew(description)
    use_three_columns = len(description) > settings.description_three_columns_threshold
    use_two_columns = len(description) > settings.description_two_columns_threshold

    day_num, progress_percent = _calculate_progress(
        step, step_index, steps, trip_data, use_step_range=use_step_range
    )

    box_center_position, arrow_bar_position = _calculate_progress_positions(progress_percent)

    country_map_svg, map_dot_x, map_dot_y = _extract_map_data(map_result)

    date = datetime.fromtimestamp(step.start_time, ZoneInfo(step.timezone_id))
    coords_lat, coords_lon = (
        Point(round(step.location.lat, 4), round(step.location.lon, 4)).format_unicode().split(",")
    )

    day_temp_api = weather_data.day_temp
    night_temp = weather_data.night_temp
    day_feels_like = weather_data.day_feels_like
    night_feels_like = weather_data.night_feels_like

    if day_temp_api is not None and step.weather_temperature is not None:
        temp_diff = abs(day_temp_api - step.weather_temperature)
        if temp_diff > settings.temperature_mismatch_threshold:
            logger.warning(
                "Temperature mismatch for %s on %s: API reports %.1f°C, "
                "trip data has %.1f°C (difference: %.1f°C). Using API data.",
                step.city,
                date.strftime("%Y-%m-%d"),
                day_temp_api,
                step.weather_temperature,
                temp_diff,
            )

    day_weather_icon_url, night_weather_icon_url = _extract_weather_icons(weather_data, step)

    country_flag_data_uri = flag_result.flag_url if flag_result else None
    accent_color = flag_result.accent_color if flag_result else None

    day_temp_display = day_temp_api
    temp_str = _format_temperature(day_temp_display, day_feels_like)
    temp_night_str = _format_temperature(night_temp, night_feels_like)

    return StepData(
        city=step.city,
        country=step.country,
        country_code=step.country_code,
        coords_lat=coords_lat,
        coords_lon=coords_lon,
        date_month=date.strftime("%B"),
        date_day=str(date.day),
        weather=_format_weather_condition(step.weather_condition),
        day_weather_icon_url=day_weather_icon_url,
        night_weather_icon_url=night_weather_icon_url,
        temp_str=temp_str,
        temp_night_str=temp_night_str,
        altitude_str=format_altitude(elevation),
        day_num=day_num,
        progress_percent=progress_percent,
        day_counter_box_position=box_center_position,
        day_counter_arrow_position=arrow_bar_position,
        cover_image_path=cover_image_path,
        country_flag_data_uri=country_flag_data_uri,
        country_map_svg=country_map_svg,
        map_dot_x=map_dot_x,
        map_dot_y=map_dot_y,
        accent_color=accent_color,
        description=description,
        desc_dir="rtl" if is_hebrew_text else "ltr",
        desc_align="right" if is_hebrew_text else "left",
        use_two_columns=use_two_columns,
        use_three_columns=use_three_columns,
        light_mode=light_mode,
        photo_pages=[],  # Will be populated later
    )


@cache
def _format_weather_condition(condition: str | None) -> str:
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


def _format_temperature(temp: float | None, feels_like: float | None) -> str:
    if temp is None:
        return "N/A"
    # Only show feels like if difference is meaningful
    # Using module-level settings
    if feels_like is not None and abs(feels_like - temp) >= settings.feels_like_display_threshold:
        return f"{int(temp)}° ({int(feels_like)}°)"
    return f"{int(temp)}°"

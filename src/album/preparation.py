"""Step data preparation for HTML generation."""

from datetime import datetime
from zoneinfo import ZoneInfo

from geopy import Point

from src.core.logger import get_logger
from src.core.settings import settings
from src.core.text import is_hebrew
from src.data.context import StepTemplateContext
from src.data.models import (
    MapData,
    Step,
    StepContext,
    StepExternalData,
    Trip,
)
from src.services.altitude import format_altitude

logger = get_logger(__name__)


def _calculate_progress(
    step: Step,
    step_index: int,
    steps: list[Step],
    trip: Trip,
    *,
    use_step_range: bool,
) -> tuple[int, float]:
    if use_step_range:
        day_num = step_index + 1
        progress_percent = (day_num / len(steps)) * 100 if steps else 0
    else:
        day_num = _calculate_day_number(step.date.timestamp(), trip.start_date, trip.timezone_id)
        total_days = _calculate_day_number(trip.end_date, trip.start_date, trip.timezone_id)
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


def _extract_map_data(
    map_result: MapData | None,
) -> tuple[str | None, float | None, float | None]:
    if map_result:
        map_dot_x, map_dot_y = map_result.dot_position if map_result.dot_position else (None, None)
        return map_result.svg_content, map_dot_x, map_dot_y
    return None, None, None


def prepare_step_data(
    context: StepContext,
    external_data: StepExternalData,
    *,
    use_step_range: bool,
    light_mode: bool = False,
) -> StepTemplateContext:
    is_hebrew_text = is_hebrew(context.step.description)

    day_num, progress_percent = _calculate_progress(
        context.step,
        context.step_index,
        context.steps,
        context.trip,
        use_step_range=use_step_range,
    )

    country_map_svg, map_dot_x, map_dot_y = _extract_map_data(external_data.map_data)

    coords_lat, coords_lon = (
        Point(round(context.step.location.lat, 4), round(context.step.location.lon, 4))
        .format_unicode()
        .split(",")
    )

    return StepTemplateContext(
        id=context.step.id,
        name=context.step.name,
        country=context.step.location.detail,
        country_code=context.step.location.country_code,
        coords_lat=coords_lat,
        coords_lon=coords_lon,
        lat_val=context.step.location.lat,
        lon_val=context.step.location.lon,
        date_month=context.step.date.strftime("%B"),
        date_day=str(context.step.date.day),
        day_weather_icon_url=(
            settings.weather_icon_url.format(icon_name=external_data.weather_data.day_icon)
            if external_data.weather_data.day_icon
            else None
        ),
        night_weather_icon_url=(
            settings.weather_icon_url.format(icon_name=external_data.weather_data.night_icon)
            if external_data.weather_data.night_icon
            else None
        ),
        temp_str=(
            _format_temperature(
                external_data.weather_data.day_temp, external_data.weather_data.day_feels_like
            )
        ),
        temp_night_str=(
            _format_temperature(
                external_data.weather_data.night_temp, external_data.weather_data.night_feels_like
            )
        ),
        altitude_str=format_altitude(external_data.elevation),
        day_num=day_num,
        progress_percent=progress_percent,
        day_counter_box_position=max(5.0, min(progress_percent, 95.0)),
        day_counter_arrow_position=max(1.0, min(progress_percent, 99.0)),
        cover_photo_path=external_data.cover_photo_path,
        cover_photo_id=external_data.cover_photo_id,
        country_flag_data_uri=(
            external_data.flag_data.flag_url if external_data.flag_data else None
        ),
        country_map_svg=country_map_svg,
        map_dot_x=map_dot_x,
        map_dot_y=map_dot_y,
        accent_color=(external_data.flag_data.accent_color if external_data.flag_data else None),
        description=context.step.description,
        desc_dir="rtl" if is_hebrew_text else "ltr",
        desc_align="right" if is_hebrew_text else "left",
        use_two_columns=(
            len(context.step.description) > settings.description_two_columns_threshold
        ),
        use_three_columns=(
            len(context.step.description) > settings.description_three_columns_threshold
        ),
        light_mode=light_mode,
        photo_pages=[],  # Will be populated later
    )


def _format_temperature(temp: float | None, feels_like: float | None) -> str:
    if temp is None:
        return "N/A"
    # Only show feels like if difference is meaningful
    # Using module-level settings
    if feels_like is not None and abs(feels_like - temp) >= settings.feels_like_display_threshold:
        return f"{int(temp)}° ({int(feels_like)}°)"
    return f"{int(temp)}°"

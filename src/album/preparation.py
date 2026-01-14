"""Step data preparation for HTML generation."""

from geopy.point import Point

from src.core.logger import get_logger
from src.core.settings import settings
from src.core.text import is_hebrew
from src.data.context import StepTemplateCtx
from src.data.models import (
    StepContext,
)

logger = get_logger(__name__)


def prepare_step_template(context: StepContext) -> StepTemplateCtx:
    is_hebrew_text = is_hebrew(context.step.description)

    progress = 100 * context.step_index / (len(context.steps) - 1)
    # TODO(itay): altitude here?
    coords_lat, coords_lon = str(
        Point(
            round(context.step.location.lat, 4), round(context.step.location.lon, 4)
        ).format_unicode()
    ).split(",")

    return StepTemplateCtx(
        id=context.step.id,
        name=context.step.name,
        country=context.step.location.country,
        coords_lat=coords_lat,
        coords_lon=coords_lon,
        lat_val=context.step.location.lat,
        lon_val=context.step.location.lon,
        date_month=context.step.date.strftime("%B"),
        date_day=str(context.step.date.day),
        day_weather_icon_url=(
            settings.weather_icon_url.format(icon_name=context.step.weather.day_icon)
        ),
        night_weather_icon_url=(
            settings.weather_icon_url.format(icon_name=context.step.weather.night_icon)
        ),
        temp_str=(
            _format_temperature(context.step.weather.day_temp, context.step.weather.day_feels_like)
        ),
        temp_night_str=(
            _format_temperature(
                context.step.weather.night_temp, context.step.weather.night_feels_like
            )
        ),
        altitude_str=f"{round(context.step.altitude):,}",
        day_num=(context.step_index + 1),
        progress_percent=progress,
        day_counter_box_position=max(6.0, min(progress, 94.0)),
        day_counter_arrow_position=max(1.0, min(progress, 99.0)),
        cover_photo=context.cover_photo,
        country_flag_data_uri=context.step.flag.flag_url,
        country_map_svg=context.step.map.svg_content,
        map_dot_x=context.step.map.dot_position[0],
        map_dot_y=context.step.map.dot_position[1],
        accent_color=context.step.flag.accent_color,
        description=context.step.description,
        desc_dir="rtl" if is_hebrew_text else "ltr",
        desc_align="right" if is_hebrew_text else "left",
        use_two_columns=(
            len(context.step.description) > settings.description_two_columns_threshold
        ),
        use_three_columns=(
            len(context.step.description) > settings.description_three_columns_threshold
        ),
        # Will be populated later
        photo_pages=[],
        hidden_photos=[],
    )


def _format_temperature(temp: float | None, feels_like: float | None) -> str:
    if temp is None:
        return "N/A"
    if feels_like is not None and abs(feels_like - temp) >= settings.feels_like_display_threshold:
        return f"{int(temp)}° ({int(feels_like)}°)"
    return f"{int(temp)}°"

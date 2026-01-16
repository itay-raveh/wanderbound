"""Step data preparation for HTML generation."""

from collections.abc import Sequence

from geopy.point import Point

from src.core.logger import get_logger
from src.core.settings import settings
from src.core.text import choose_text_dir
from src.data.context import StepTemplateCtx
from src.data.layout import StepLayout
from src.data.trip import EnrichedStep

logger = get_logger(__name__)


def build_step_template_ctx(
    step: EnrichedStep,
    layout: StepLayout,
    step_index: int,
    steps: Sequence[EnrichedStep],
) -> StepTemplateCtx:
    progress = 100 * step_index / (len(steps) - 1) if len(steps) > 1 else 0
    coords_lat, coords_lon = str(
        Point(round(step.location.lat, 4), round(step.location.lon, 4)).format_unicode()
    ).split(",")

    return StepTemplateCtx(
        id=step.id,
        name=step.name,
        country=step.location.country,
        coords_lat=coords_lat,
        coords_lon=coords_lon,
        lat_val=step.location.lat,
        lon_val=step.location.lon,
        date_month=step.date.strftime("%B"),
        date_day=str(step.date.day),
        day_weather_icon_url=(settings.weather_icon_url.format(icon_name=step.weather.day_icon)),
        night_weather_icon_url=(
            settings.weather_icon_url.format(icon_name=step.weather.night_icon)
        ),
        temp_str=(_format_temperature(step.weather.day_temp, step.weather.day_feels_like)),
        temp_night_str=(
            _format_temperature(step.weather.night_temp, step.weather.night_feels_like)
        ),
        altitude_str=f"{round(step.altitude):,}",
        day_num=(step_index + 1),
        progress_percent=progress,
        day_counter_box_position=max(6.0, min(progress, 94.0)),
        day_counter_arrow_position=max(1.0, min(progress, 99.0)),
        cover_photo=layout.cover,
        country_flag_data_uri=step.flag.flag_url,
        country_map_svg=step.map.svg_content,
        map_dot_x=step.map.dot_position[0],
        map_dot_y=step.map.dot_position[1],
        accent_color=step.flag.accent_color,
        description=step.description,
        desc_dir=choose_text_dir(step.description),
        is_long_description=len(step.description) > settings.long_description_threshold,
        photo_pages=layout.pages,
        hidden_photos=layout.hidden_photos,
    )


def _format_temperature(temp: float | None, feels_like: float | None) -> str:
    if temp is None:
        return "N/A"
    if feels_like is not None and abs(feels_like - temp) >= settings.feels_like_display_threshold:
        return f"{int(temp)}° ({int(feels_like)}°)"
    return f"{int(temp)}°"

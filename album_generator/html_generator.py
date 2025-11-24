"""Generate HTML pages for the photo album using Jinja templates."""

import base64
from datetime import datetime
from pathlib import Path
from typing import Any

import pytz
from jinja2 import Environment, FileSystemLoader
from langdetect import LangDetectException, detect

from .apis import (
    extract_prominent_color_from_flag,
    format_altitude,
    get_altitude_batch,
    get_country_flag_data_uri,
    get_country_map_data_uri,
    get_country_map_dot_position,
    get_country_map_svg,
)
from .apis.weather import WeatherData, get_weather_data
from .constants import (
    DESCRIPTION_THREE_COLUMNS_THRESHOLD,
    DESCRIPTION_TWO_COLUMNS_THRESHOLD,
    FEELS_LIKE_DISPLAY_THRESHOLD,
    TEMPERATURE_MISMATCH_THRESHOLD,
)
from .data_loader import (
    calculate_day_number,
    format_coordinates,
    format_date,
    format_weather_condition,
)
from .logger import create_progress, get_console, get_logger
from .models import Photo, Step, TripData
from .settings import get_settings

logger = get_logger(__name__)
console = get_console()


def image_to_data_uri(image_path: Path) -> str:
    """Convert image to data URI for embedding in HTML."""
    import mimetypes

    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = "image/jpeg"

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{image_data}"


def copy_assets(font_path: Path, output_dir: Path) -> str:
    """Copy assets (fonts, etc.) to output directory and return font path."""
    import shutil

    assets_dir = output_dir / "assets"
    fonts_dir = assets_dir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)

    output_font = fonts_dir / "Renner.ttf"
    if not output_font.exists() and font_path.exists():
        shutil.copy2(font_path, output_font)

    return "assets/fonts/Renner.ttf"


def _is_hebrew(text: str) -> bool:
    """Check if text is Hebrew using fast Unicode check first, then langdetect if needed."""
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
    """Split description into columns. Returns full text for CSS column handling."""
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
        Formatted temperature string (e.g., "25°C" or "25°C (28°C)" or "N/A")
    """
    if temp is None:
        return "N/A"
    # Only show feels like if difference is meaningful
    if (
        feels_like is not None
        and abs(feels_like - temp) >= FEELS_LIKE_DISPLAY_THRESHOLD
    ):
        return f"{int(temp)}°C ({int(feels_like)}°C)"
    return f"{int(temp)}°C"


def _calculate_progress(
    step: Step,
    step_index: int,
    steps: list[Step],
    trip_data: TripData,
    use_step_range: bool,
) -> tuple[int, float]:
    """Calculate day number and progress percentage for a step.

    Args:
        step: The step to calculate progress for
        step_index: Zero-based index of this step in the steps list
        steps: Complete list of all steps being rendered
        trip_data: Trip metadata including start/end dates and timezone
        use_step_range: If True, calculate based on step range (1 to len(steps));
                       if False, calculate based on trip days from start_date

    Returns:
        Tuple of (day_number, progress_percent) where progress_percent is 0-100
    """
    if use_step_range:
        if not steps:
            return (1, 0)

        first_step = steps[0]
        tz = pytz.timezone(first_step.timezone_id)
        first_date = datetime.fromtimestamp(first_step.start_time, tz=tz).date()
        current_date = datetime.fromtimestamp(step.start_time, tz=tz).date()
        day_num = (current_date - first_date).days + 1

        last_step = steps[-1]
        last_date = datetime.fromtimestamp(last_step.start_time, tz=tz).date()
        total_days = max(1, (last_date - first_date).days + 1)
    else:
        day_num = calculate_day_number(
            step.start_time, trip_data.start_date, trip_data.timezone_id
        )
        total_days = 1
        if trip_data.start_date and trip_data.end_date:
            tz = pytz.timezone(trip_data.timezone_id)
            start_dt = datetime.fromtimestamp(trip_data.start_date, tz=tz)
            end_dt = datetime.fromtimestamp(trip_data.end_date, tz=tz)
            total_days = max(1, (end_dt.date() - start_dt.date()).days + 1)

    progress_percent = min(100, (day_num / total_days) * 100) if total_days > 0 else 0
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
    cover_image_data_uri: str | None,
    light_mode: bool = False,
) -> dict[str, Any]:
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
        cover_image_data_uri: Base64-encoded cover image data URI or None
        light_mode: If True, use light mode color scheme; if False, use dark mode

    Returns:
        Dictionary containing all template variables for rendering this step
    """
    description = _clean_description(step.description or "")

    is_hebrew = _is_hebrew(description)
    use_three_columns = len(description) > DESCRIPTION_THREE_COLUMNS_THRESHOLD
    use_two_columns = (
        len(description) > DESCRIPTION_TWO_COLUMNS_THRESHOLD or use_three_columns
    )

    desc_col1, desc_col2, desc_col3 = _split_description(
        description, is_hebrew, use_three_columns
    )

    day_num, progress_percent = _calculate_progress(
        step, step_index, steps, trip_data, use_step_range
    )

    arrow_bar_position = max(1.0, min(99.0, progress_percent))
    box_center_position = max(9.0, min(91.0, progress_percent))

    # Extract map data (already fetched in batch)
    map_dot_x, map_dot_y = None, None
    country_map_data_uri = None
    country_map_svg = None
    if map_data:
        country_map_data_uri, country_map_svg, dot_pos = map_data
        if dot_pos:
            map_dot_x, map_dot_y = dot_pos

    # Extract weather data (already fetched in batch)
    day_temp_api = weather_data.day_temp
    night_temp = weather_data.night_temp
    day_feels_like = weather_data.day_feels_like
    night_feels_like = weather_data.night_feels_like
    day_icon_api = weather_data.day_icon
    night_icon = weather_data.night_icon

    date_data = format_date(step.start_time, step.timezone_id)
    coords_data = format_coordinates(step.location.lat, step.location.lon)

    # Compare API day temperature with trip data temperature
    use_trip_data = False
    if day_temp_api is not None and step.weather_temperature is not None:
        temp_diff = abs(day_temp_api - step.weather_temperature)
        if temp_diff > TEMPERATURE_MISMATCH_THRESHOLD:
            logger.warning(
                f"Temperature mismatch for {step.city} on {date_data['month']} {date_data['day']}: "
                f"API reports {day_temp_api:.1f}°C, trip data has {step.weather_temperature:.1f}°C "
                f"(difference: {temp_diff:.1f}°C). Using trip data."
            )
            use_trip_data = True

    # Use trip data if there's a mismatch, otherwise use API data
    if use_trip_data:
        # Use trip data for day weather
        day_icon_name = None
        if step.weather_condition:
            day_icon_name = step.weather_condition.lower().replace("_", "-")
    else:
        # Use API day icon if available, otherwise fall back to trip data weather condition
        day_icon_name = day_icon_api
        if not day_icon_name and step.weather_condition:
            # Fallback to trip data weather condition
            day_icon_name = step.weather_condition.lower().replace("_", "-")

    # Generate icon URLs
    settings = get_settings()
    day_weather_icon_url = None
    night_weather_icon_url = None

    if day_icon_name:
        day_weather_icon_url = settings.weather_icon_url.format(icon_name=day_icon_name)
    if night_icon:
        night_weather_icon_url = settings.weather_icon_url.format(icon_name=night_icon)

    # Extract flag data (already fetched in batch)
    country_flag_data_uri = None
    accent_color = None
    if flag_data:
        country_flag_data_uri, accent_color = flag_data

    # Format temperatures with feels like if available
    day_temp_display = step.weather_temperature if use_trip_data else day_temp_api
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
        "cover_image_data_uri": cover_image_data_uri,
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


def generate_album_html(
    steps: list[Step],
    steps_with_photos: dict[int, list[Photo]],
    steps_cover_photos: dict[int, Photo | None],
    steps_photo_pages: dict[int, list[list[Photo]]],
    trip_data: TripData,
    font_path: Path,
    output_path: Path,
    use_step_range: bool = False,
    light_mode: bool = False,
) -> Path:
    """Generate HTML album file from trip data and photos.

    Args:
        steps: List of steps to include in the album
        steps_with_photos: Dictionary mapping step IDs to lists of Photo objects
        steps_cover_photos: Dictionary mapping step IDs to cover Photo (or None)
        steps_photo_pages: Dictionary mapping step IDs to lists of photo pages (each page is a list of Photos)
        trip_data: Trip metadata including start/end dates, timezone, and all steps
        font_path: Path to the font file to use for titles
        output_path: Path where the HTML file should be written
        use_step_range: If True, progress bars use step range (1 to len(steps));
                       if False, progress bars use trip days from start_date
        light_mode: If True, use light mode color scheme; if False, use dark mode

    Returns:
        Path to the generated HTML file
    """
    font_rel_path = copy_assets(font_path, output_path.parent)

    # Batch fetch altitudes
    with console.status("[bold blue]Fetching altitudes..."):
        logger.debug("Fetching altitudes...")
        locations = [(step.location.lat, step.location.lon) for step in steps]
        elevations = get_altitude_batch(locations)
    logger.debug(f"Fetched {len(elevations)} altitude values")

    # Batch fetch weather data
    logger.debug("Fetching weather data...")
    weather_progress = create_progress("Fetching weather data")
    weather_data_list: list[WeatherData] = []
    with weather_progress:
        task_id = weather_progress.add_task("Fetching weather data", total=len(steps))
        for step in weather_progress.track(steps, task_id=task_id):
            weather_progress.update(
                task_id, description=f"Fetching weather data: {step.city}"
            )
            weather_data = get_weather_data(
                step.location.lat,
                step.location.lon,
                step.start_time,
                step.timezone_id,
            )
            weather_data_list.append(weather_data)
        weather_progress.update(task_id, description="Fetching weather data")
    logger.debug(f"Fetched {len(weather_data_list)} weather data entries")

    # Batch fetch flags and accent colors
    logger.debug("Fetching flags and extracting colors...")
    flag_progress = create_progress("Processing flags")
    flag_data_list = []
    with flag_progress:
        task_id = flag_progress.add_task("Processing flags", total=len(steps))
        for step in flag_progress.track(steps, task_id=task_id):
            flag_progress.update(
                task_id, description=f"Processing flags: {step.country}"
            )
            country_flag_data_uri = (
                get_country_flag_data_uri(step.country_code)
                if step.country_code
                else None
            )
            accent_color = extract_prominent_color_from_flag(
                country_flag_data_uri, step.country_code, light_mode
            )
            flag_data_list.append((country_flag_data_uri, accent_color))
        flag_progress.update(task_id, description="Processing flags")
    logger.debug(f"Processed {len(flag_data_list)} flags")

    # Batch fetch maps and calculate dot positions
    logger.debug("Fetching maps and calculating positions...")
    map_progress = create_progress("Processing maps")
    map_data_list = []
    with map_progress:
        task_id = map_progress.add_task("Processing maps", total=len(steps))
        for step in map_progress.track(steps, task_id=task_id):
            map_progress.update(task_id, description=f"Processing maps: {step.country}")
            if step.country_code:
                country_map_data_uri = get_country_map_data_uri(
                    step.country_code, step.location.lat, step.location.lon
                )
                country_map_svg = get_country_map_svg(
                    step.country_code, step.location.lat, step.location.lon
                )
                dot_pos = get_country_map_dot_position(
                    step.country_code, step.location.lat, step.location.lon
                )
                map_data_list.append((country_map_data_uri, country_map_svg, dot_pos))
            else:
                map_data_list.append((None, None, None))
        map_progress.update(task_id, description="Processing maps")
    logger.debug(f"Processed {len(map_data_list)} maps")

    # Batch convert cover images to data URIs
    logger.debug("Converting cover images to data URIs...")
    image_progress = create_progress("Processing images")
    cover_image_data_uri_list: list[str | None] = []
    with image_progress:
        task_id = image_progress.add_task("Processing images", total=len(steps))
        for _idx, step in enumerate(image_progress.track(steps, task_id=task_id)):
            image_progress.update(
                task_id, description=f"Processing images: {step.city}"
            )
            cover_photo = steps_cover_photos.get(step.id) if step.id else None
            # Check if we need two columns (determines if we need image data URI)
            # Match the logic from prepare_step_data
            description = _clean_description(step.description or "")
            use_three_columns = len(description) > DESCRIPTION_THREE_COLUMNS_THRESHOLD
            use_two_columns = (
                len(description) > DESCRIPTION_TWO_COLUMNS_THRESHOLD
                or use_three_columns
            )
            if cover_photo and cover_photo.path.exists() and not use_two_columns:
                cover_image_data_uri_list.append(image_to_data_uri(cover_photo.path))
            else:
                cover_image_data_uri_list.append(None)
        image_progress.update(task_id, description="Processing images")
    logger.debug(f"Processed {len(cover_image_data_uri_list)} cover images")

    # Prepare template environment
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("album.html")

    # Prepare step data
    logger.debug("Preparing step data...")
    step_data_list = []

    progress = create_progress("Preparing steps")

    with progress:
        task_id = progress.add_task("Preparing steps", total=len(steps))
        for idx, (
            step,
            elevation,
            weather_data,
            flag_data,
            map_data,
            cover_image_data_uri,
        ) in enumerate(
            progress.track(
                zip(
                    steps,
                    elevations,
                    weather_data_list,
                    flag_data_list,
                    map_data_list,
                    cover_image_data_uri_list,
                    strict=True,
                ),
                task_id=task_id,
            )
        ):
            logger.debug(f"Processing step {idx + 1}/{len(steps)}: {step.city}")
            progress.update(task_id, description=f"Preparing steps: {step.city}")

            cover_photo = steps_cover_photos.get(step.id) if step.id else None
            photo_pages = steps_photo_pages.get(step.id, []) if step.id else []

            # Convert photo pages to data URIs for template
            photo_pages_data_uris: list[list[str]] = []
            for page in photo_pages:
                page_data_uris: list[str] = []
                for photo in page:
                    if photo.path.exists():
                        page_data_uris.append(image_to_data_uri(photo.path))
                if page_data_uris:
                    photo_pages_data_uris.append(page_data_uris)

            step_data = prepare_step_data(
                step,
                cover_photo,
                idx,
                steps,
                trip_data,
                use_step_range,
                elevation,
                weather_data,
                flag_data,
                map_data,
                cover_image_data_uri,
                light_mode,
            )
            # Add photo pages to step data
            step_data["photo_pages"] = photo_pages_data_uris
            step_data_list.append(step_data)

        progress.update(task_id, description="Preparing steps")

    logger.debug("Step data prepared")

    # Render template
    html = template.render(
        steps=step_data_list, font_path=font_rel_path, light_mode=light_mode
    )

    # Write to file
    output_path.write_text(html, encoding="utf-8")

    return output_path

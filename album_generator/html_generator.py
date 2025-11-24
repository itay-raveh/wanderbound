"""Generate HTML pages for the photo album using Jinja templates."""

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
    CSS_DIR,
    FONT_FILE,
    PROGRESS_BOX_MAX_POSITION,
    PROGRESS_BOX_MIN_POSITION,
    PROGRESS_MAX_POSITION,
    PROGRESS_MIN_POSITION,
    STATIC_DIR,
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


def copy_image_to_assets(
    image_path: Path, output_dir: Path, step_name: str, photo_index: int
) -> str:
    """Copy image to assets directory and return relative path.

    Args:
        image_path: Path to source image file
        output_dir: Output directory (parent of assets/)
        step_name: Step name (e.g., "Buenos Aires (Argentina)") - matches photos_by_pages.txt
        photo_index: Photo index within the step (matches photos_by_pages.txt)

    Returns:
        Relative path to copied image (e.g., "assets/images/Buenos_Aires_Argentina_photo_0.jpg")
    """
    import re
    import shutil

    from .constants import ASSETS_DIR, IMAGES_DIR

    assets_dir = output_dir / ASSETS_DIR
    images_dir = assets_dir / IMAGES_DIR
    images_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize step name for filesystem: replace spaces, parentheses, colons with underscores
    sanitized_name = re.sub(r"[^\w\-]", "_", step_name)
    sanitized_name = re.sub(r"_+", "_", sanitized_name)  # Collapse multiple underscores
    sanitized_name = sanitized_name.strip("_")  # Remove leading/trailing underscores

    # Get file extension from source
    ext = image_path.suffix.lower() or ".jpg"
    output_filename = f"{sanitized_name}_photo_{photo_index}{ext}"
    output_path = images_dir / output_filename

    # Copy image if it doesn't exist
    if not output_path.exists() and image_path.exists():
        shutil.copy2(image_path, output_path)

    from .constants import ASSETS_DIR

    return f"{ASSETS_DIR}/{IMAGES_DIR}/{output_filename}"


def copy_assets(font_path: Path, output_dir: Path) -> None:
    """Copy assets (fonts, CSS, etc.) to output directory."""
    import shutil

    assets_dir = output_dir / "assets"
    fonts_dir = assets_dir / "fonts"
    css_dir = assets_dir / "css"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    css_dir.mkdir(parents=True, exist_ok=True)

    # Copy font
    output_font = fonts_dir / FONT_FILE
    if not output_font.exists() and font_path.exists():
        shutil.copy2(font_path, output_font)

    # Copy CSS files (no longer need templating - using CSS media queries and classes)
    static_dir = Path(__file__).parent / STATIC_DIR / CSS_DIR
    css_files = [
        "variables.css",
        "reset.css",
        "layout.css",
        "components.css",
        "typography.css",
        "photos.css",
    ]

    for css_file in css_files:
        source_css = static_dir / css_file
        output_css = css_dir / css_file
        if source_css.exists():
            shutil.copy2(source_css, output_css)


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
        Formatted temperature string (e.g., "25°" or "25° (28°)" or "N/A")
    """
    if temp is None:
        return "N/A"
    # Only show feels like if difference is meaningful
    settings = get_settings()
    if (
        feels_like is not None
        and abs(feels_like - temp) >= settings.feels_like_display_threshold
    ):
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
    cover_image_path: str | None,
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
        len(description) > settings.description_two_columns_threshold
        or use_three_columns
    )

    desc_col1, desc_col2, desc_col3 = _split_description(
        description, is_hebrew, use_three_columns
    )

    day_num, progress_percent = _calculate_progress(
        step, step_index, steps, trip_data, use_step_range
    )

    arrow_bar_position = max(
        PROGRESS_MIN_POSITION, min(PROGRESS_MAX_POSITION, progress_percent)
    )
    # For very low progress (first day), position box at a safe minimum
    # The translateX(-55%) moves it left by 55% of its width, so we need enough margin
    # Estimate box width ~60px, container ~400px, so need ~6% minimum to avoid going negative
    # For high progress (final day), cap at 95% to ensure box doesn't go off right edge
    if progress_percent < PROGRESS_BOX_MIN_POSITION:
        box_center_position = PROGRESS_BOX_MIN_POSITION
    elif progress_percent > PROGRESS_BOX_MAX_POSITION:
        box_center_position = PROGRESS_BOX_MAX_POSITION
    else:
        box_center_position = progress_percent

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

    # Compare API day temperature with trip data temperature (for logging only)
    # Always use API data as it's more accurate
    settings = get_settings()
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


def generate_album_html(
    steps: list[Step],
    steps_with_photos: dict[int, list[Photo]],
    steps_cover_photos: dict[int, Photo | None],
    steps_photo_pages: dict[int, list[list[Photo]]],
    steps_photo_page_layouts: dict[int, list[bool]],
    steps_photo_page_portrait_split_layouts: dict[int, list[bool]],
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
        steps_photo_page_layouts: Dictionary mapping step IDs to lists of layout flags (True for 3-portrait layout)
        steps_photo_page_portrait_split_layouts: Dictionary mapping step IDs to lists of layout flags (True for portrait-landscape split layout)
        trip_data: Trip metadata including start/end dates, timezone, and all steps
        font_path: Path to the font file to use for titles
        output_path: Path where the HTML file should be written
        use_step_range: If True, progress bars use step range (1 to len(steps));
                       if False, progress bars use trip days from start_date
        light_mode: If True, use light mode color scheme; if False, use dark mode

    Returns:
        Path to the generated HTML file
    """
    copy_assets(font_path, output_path.parent)

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

    # Batch copy cover images to assets directory
    logger.debug("Copying cover images to assets...")
    image_progress = create_progress("Processing images")
    cover_image_path_list: list[str | None] = []
    with image_progress:
        task_id = image_progress.add_task("Processing images", total=len(steps))
        for _idx, step in enumerate(image_progress.track(steps, task_id=task_id)):
            image_progress.update(
                task_id, description=f"Processing images: {step.city}"
            )
            cover_photo = steps_cover_photos.get(step.id) if step.id else None
            # Check if we need two columns (determines if we need image)
            # Match the logic from prepare_step_data
            description = _clean_description(step.description or "")
            settings = get_settings()
            use_three_columns = (
                len(description) > settings.description_three_columns_threshold
            )
            use_two_columns = (
                len(description) > settings.description_two_columns_threshold
                or use_three_columns
            )
            if cover_photo and cover_photo.path.exists() and not use_two_columns:
                step_name = step.get_name_for_photos_export()
                cover_image_path_list.append(
                    copy_image_to_assets(
                        cover_photo.path,
                        output_path.parent,
                        step_name,
                        cover_photo.index,
                    )
                )
            else:
                cover_image_path_list.append(None)
        image_progress.update(task_id, description="Processing images")
    logger.debug(f"Processed {len(cover_image_path_list)} cover images")

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
            cover_image_path,
        ) in enumerate(
            progress.track(
                zip(
                    steps,
                    elevations,
                    weather_data_list,
                    flag_data_list,
                    map_data_list,
                    cover_image_path_list,
                    strict=True,
                ),
                task_id=task_id,
            )
        ):
            logger.debug(f"Processing step {idx + 1}/{len(steps)}: {step.city}")
            progress.update(task_id, description=f"Preparing steps: {step.city}")

            cover_photo = steps_cover_photos.get(step.id) if step.id else None
            photo_pages = steps_photo_pages.get(step.id, []) if step.id else []
            photo_page_layouts = (
                steps_photo_page_layouts.get(step.id, []) if step.id else []
            )
            photo_page_portrait_split_layouts = (
                steps_photo_page_portrait_split_layouts.get(step.id, [])
                if step.id
                else []
            )

            # Copy photo pages images to assets directory
            photo_pages_paths: list[dict[str, Any]] = []
            step_name = step.get_name_for_photos_export()
            for page_idx, page in enumerate(photo_pages):
                page_paths: list[str] = []
                for photo in page:
                    if photo.path.exists():
                        page_paths.append(
                            copy_image_to_assets(
                                photo.path, output_path.parent, step_name, photo.index
                            )
                        )
                if page_paths:
                    # Get the layout flags for this page
                    # photo_page_layouts should have the same length as photo_pages
                    is_three_portraits = False
                    is_portrait_landscape_split = False
                    if page_idx < len(photo_page_layouts):
                        is_three_portraits = photo_page_layouts[page_idx]
                    if page_idx < len(photo_page_portrait_split_layouts):
                        is_portrait_landscape_split = photo_page_portrait_split_layouts[
                            page_idx
                        ]

                    # Safety check: if we have exactly 3 photos, double-check the layout
                    # This ensures the flag is set even if there was a mismatch in the layout array
                    if len(page) == 3:
                        from .image_selector import (
                            _is_one_portrait_two_landscapes,
                            _is_three_portraits,
                            get_photo_ratio,
                        )

                        if _is_three_portraits(tuple(page)):
                            is_three_portraits = True
                            is_portrait_landscape_split = False
                            logger.debug(
                                f"Detected 3 portraits in html_generator, forcing layout for step {step.id} page {page_idx}"
                            )
                        elif _is_one_portrait_two_landscapes(tuple(page)):
                            is_three_portraits = False
                            is_portrait_landscape_split = True
                            logger.debug(
                                f"Detected 1 portrait + 2 landscapes in html_generator, forcing split layout for step {step.id} page {page_idx}"
                            )
                        else:
                            # Check what we actually have
                            ratios = [
                                get_photo_ratio(p.width or 0, p.height or 0)
                                for p in page
                            ]
                            logger.debug(
                                f"Page with 3 photos but no special layout in html_generator. Step {step.id} page {page_idx}, "
                                f"ratios: {[r.name for r in ratios]}, dimensions: {[(p.width, p.height) for p in page]}"
                            )

                    photo_pages_paths.append(
                        {
                            "photos": page_paths,
                            "is_three_portraits": is_three_portraits,
                            "is_portrait_landscape_split": is_portrait_landscape_split,
                        }
                    )

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
                cover_image_path,
                light_mode,
            )
            # Add photo pages to step data
            step_data["photo_pages"] = photo_pages_paths
            step_data_list.append(step_data)

        progress.update(task_id, description="Preparing steps")

    logger.debug("Step data prepared")

    # Render template
    html = template.render(steps=step_data_list, light_mode=light_mode)

    # Write to file
    output_path.write_text(html, encoding="utf-8")

    return output_path

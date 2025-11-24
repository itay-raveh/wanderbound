"""Generate HTML pages for the photo album using Jinja templates."""

from pathlib import Path
from typing import Optional
import base64
from datetime import datetime
import pytz
from jinja2 import Environment, FileSystemLoader
from langdetect import detect, LangDetectException

from .models import Step, TripData
from .logger import get_logger, DEBUG_MODE, create_progress, get_console
from .constants import (
    DESCRIPTION_THREE_COLUMNS_THRESHOLD,
    DESCRIPTION_TWO_COLUMNS_THRESHOLD,
    WEATHER_ICON_BASE_URL,
)

logger = get_logger(__name__)
console = get_console()
from .data_loader import (
    format_coordinates,
    format_date,
    format_weather_condition,
    calculate_day_number,
)
from .apis import (
    get_altitude_batch,
    format_altitude,
    get_country_flag_data_uri,
    get_country_map_data_uri,
    get_country_map_svg,
    get_country_map_dot_position,
    extract_prominent_color_from_flag,
)


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
    if has_hebrew_chars:
        # If we found Hebrew characters, it's likely Hebrew text
        # Only use langdetect for very short texts that might be ambiguous
        if len(text.strip()) > 10:
            return True

    # Use langdetect for mixed content or short texts
    try:
        detected_lang = detect(text)
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


def _calculate_progress(
    step: Step,
    step_index: int,
    steps: list[Step],
    trip_data: TripData,
    use_step_range: bool,
) -> tuple[int, float]:
    """Calculate day number and progress percentage."""
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
    image_path: Optional[Path],
    step_index: int,
    steps: list[Step],
    trip_data: TripData,
    use_step_range: bool,
    elevation: Optional[float],
    light_mode: bool = False,
) -> dict:
    """Prepare all data needed for rendering a step."""
    description = step.description or ""
    if description:
        description = description.lstrip()
        lines = description.split("\n")
        cleaned_lines = []
        for line in lines:
            cleaned = line.lstrip()
            if cleaned:
                cleaned_lines.append(cleaned)
            elif cleaned_lines and cleaned_lines[-1]:
                cleaned_lines.append("")
        description = "\n".join(cleaned_lines).strip().lstrip()

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

    map_dot_x, map_dot_y = None, None
    if step.country_code:
        dot_pos = get_country_map_dot_position(
            step.country_code, step.location.lat, step.location.lon
        )
        if dot_pos:
            map_dot_x, map_dot_y = dot_pos

    weather_icon_url = None
    if step.weather_condition:
        # Use basmilius weather-icons - they use semantic names matching weather conditions
        # Direct mapping: condition name -> icon filename (no mapping dict needed)
        # Just normalize the condition name (lowercase, replace underscores with hyphens)
        icon_name = step.weather_condition.lower().replace("_", "-")

        weather_icon_url = f"{WEATHER_ICON_BASE_URL}/{icon_name}.svg"
        logger.debug(
            f"Weather condition '{step.weather_condition}' using icon '{icon_name}'"
        )

    country_flag_data_uri = (
        get_country_flag_data_uri(step.country_code) if step.country_code else None
    )
    accent_color = extract_prominent_color_from_flag(
        country_flag_data_uri, step.country_code, light_mode
    )

    return {
        "city": step.city,
        "country": step.country,
        "country_code": step.country_code,
        "coords_lat": format_coordinates(step.location.lat, step.location.lon)["lat"],
        "coords_lon": format_coordinates(step.location.lat, step.location.lon)["lon"],
        "date_month": format_date(step.start_time, step.timezone_id)["month"],
        "date_day": format_date(step.start_time, step.timezone_id)["day"],
        "weather": format_weather_condition(step.weather_condition),
        "weather_icon_url": weather_icon_url,
        "temp_str": (
            f"{int(step.weather_temperature)}°C" if step.weather_temperature else "N/A"
        ),
        "altitude_str": format_altitude(elevation),
        "day_num": day_num,
        "progress_percent": progress_percent,
        "day_counter_box_position": box_center_position,
        "day_counter_arrow_position": arrow_bar_position,
        "image_data_uri": (
            image_to_data_uri(image_path)
            if image_path and image_path.exists() and not use_two_columns
            else None
        ),
        "country_flag_data_uri": country_flag_data_uri,
        "country_map_data_uri": (
            get_country_map_data_uri(
                step.country_code, step.location.lat, step.location.lon
            )
            if step.country_code
            else None
        ),
        "country_map_svg": (
            get_country_map_svg(step.country_code, step.location.lat, step.location.lon)
            if step.country_code
            else None
        ),
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
    step_images: dict[int, Optional[Path]],
    trip_data: TripData,
    font_path: Path,
    output_path: Path,
    use_step_range: bool = False,
    light_mode: bool = False,
) -> Path:
    """Generate a single HTML file with all steps."""
    font_rel_path = copy_assets(font_path, output_path.parent)

    # Batch fetch altitudes
    with console.status("[bold blue]Fetching altitudes..."):
        logger.debug("Fetching altitudes...")
        locations = [(step.location.lat, step.location.lon) for step in steps]
        elevations = get_altitude_batch(locations)
    logger.debug(f"Fetched {len(elevations)} altitude values")

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
        for idx, (step, elevation) in enumerate(
            progress.track(zip(steps, elevations), task_id=task_id)
        ):
            logger.debug(f"Processing step {idx + 1}/{len(steps)}: {step.city}")
            progress.update(task_id, description=f"Preparing steps: {step.city}")

            image_path = step_images.get(step.id) if step.id else None
            step_data = prepare_step_data(
                step,
                image_path,
                idx,
                steps,
                trip_data,
                use_step_range,
                elevation,
                light_mode,
            )
            step_data_list.append(step_data)

        progress.update(task_id, description="Preparing steps")

    logger.debug("Step data prepared")

    # Render template
    html = template.render(
        steps=step_data_list, font_path=font_rel_path, light_mode=light_mode
    )

    # Write to file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path

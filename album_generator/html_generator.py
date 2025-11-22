"""Generate HTML pages for the photo album using Jinja templates."""
from pathlib import Path
from typing import Optional
import base64
from jinja2 import Environment, FileSystemLoader

from .models import Step, TripData
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
    get_country_map_dot_position,
)


def image_to_data_uri(image_path: Path) -> str:
    """Convert image to data URI for embedding in HTML."""
    import mimetypes
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = "image/jpeg"
    
    with open(image_path, 'rb') as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')
    
    return f"data:{mime_type};base64,{image_data}"


def copy_assets(font_path: Path, output_dir: Path) -> str:
    """Copy assets (fonts, etc.) to output directory and return font path."""
    import shutil
    
    # Create assets/fonts directory structure
    assets_dir = output_dir / "assets"
    fonts_dir = assets_dir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy font file
    output_font = fonts_dir / "Renner.ttf"
    if not output_font.exists() and font_path.exists():
        shutil.copy2(font_path, output_font)
    
    return "assets/fonts/Renner.ttf"


def prepare_step_data(
    step: Step,
    image_path: Optional[Path],
    trip_data: TripData,
) -> dict:
    """Prepare all data needed for rendering a step."""
    # Basic info
    city = step.city
    country = step.country
    country_code = step.country_code
    description = step.description or ""
    
    # Location data
    lat = step.location.lat
    lon = step.location.lon
    
    # Format coordinates
    coords = format_coordinates(lat, lon)
    
    # Date formatting
    timezone = step.timezone_id
    date_info = format_date(step.start_time, timezone)
    
    # Weather
    weather = format_weather_condition(step.weather_condition)
    temp = step.weather_temperature
    temp_str = f"{int(temp)}°C" if temp else "N/A"
    
    # Altitude will be fetched in batch later
    altitude_str = "N/A"  # Placeholder, will be updated
    
    # Day number and progress
    day_num = calculate_day_number(
        step.start_time,
        trip_data.start_date,
        trip_data.timezone_id
    )
    
    # Calculate total days for progress bar
    from datetime import datetime
    import pytz
    total_days = 1
    if trip_data.start_date and trip_data.end_date:
        tz = pytz.timezone(trip_data.timezone_id)
        start_dt = datetime.fromtimestamp(trip_data.start_date, tz=tz)
        end_dt = datetime.fromtimestamp(trip_data.end_date, tz=tz)
        total_days = max(1, (end_dt.date() - start_dt.date()).days + 1)
    
    progress_percent = min(100, (day_num / total_days) * 100) if total_days > 0 else 0
    
    # Image
    image_data_uri = ""
    if image_path and image_path.exists():
        image_data_uri = image_to_data_uri(image_path)
    
    # Country flag and map
    country_flag_data_uri = None
    country_map_data_uri = None
    map_dot_x = None
    map_dot_y = None
    
    if country_code:
        country_flag_data_uri = get_country_flag_data_uri(country_code)
        country_map_data_uri = get_country_map_data_uri(country_code, lat, lon)
        
        # Calculate approximate position of dot within country map
        dot_pos = get_country_map_dot_position(country_code, lat, lon)
        if dot_pos:
            map_dot_x, map_dot_y = dot_pos
    
    # Determine if description is Hebrew (RTL)
    is_hebrew = False
    if description:
        is_hebrew = any('\u0590' <= char <= '\u05FF' for char in description)
    desc_dir = "rtl" if is_hebrew else "ltr"
    desc_align = "right" if is_hebrew else "left"
    
    # Determine if we should use two-column text layout instead of image
    # Use two columns if description is long (more than ~500 characters)
    use_two_columns = len(description) > 500 if description else False
    
    # Split description into two columns if needed
    description_col1 = ""
    description_col2 = ""
    if use_two_columns and description:
        # Split by paragraphs or roughly in half
        paragraphs = description.split('\n\n')
        if len(paragraphs) > 1:
            # Split paragraphs between columns
            mid = len(paragraphs) // 2
            description_col1 = '\n\n'.join(paragraphs[:mid])
            description_col2 = '\n\n'.join(paragraphs[mid:])
        else:
            # Split text roughly in half
            mid = len(description) // 2
            # Try to split at a sentence or paragraph break
            for i in range(mid, max(0, mid - 200), -1):
                if description[i] in ['.', '!', '?', '\n']:
                    mid = i + 1
                    break
            description_col1 = description[:mid].strip()
            description_col2 = description[mid:].strip()
    
    return {
        "city": city,
        "country": country,
        "country_code": country_code,
        "coords_lat": coords["lat"],
        "coords_lon": coords["lon"],
        "date_month": date_info["month"],
        "date_day": date_info["day"],
        "weather": weather,
        "temp_str": temp_str,
        "altitude_str": altitude_str,
        "day_num": day_num,
        "progress_percent": progress_percent,
        "image_data_uri": image_data_uri if not use_two_columns else None,
        "country_flag_data_uri": country_flag_data_uri,
        "country_map_data_uri": country_map_data_uri,
        "map_dot_x": map_dot_x,
        "map_dot_y": map_dot_y,
        "description": description if not use_two_columns else None,  # Don't show in left panel if using two columns
        "description_col1": description_col1,
        "description_col2": description_col2,
        "desc_dir": desc_dir,
        "desc_align": desc_align,
        "use_two_columns": use_two_columns,
    }


def generate_album_html(
    steps: list[Step],
    step_images: dict[int, Optional[Path]],
    trip_data: TripData,
    font_path: Path,
    output_path: Path,
) -> Path:
    """Generate a single HTML file with all steps."""
    # Copy assets and get font path (relative to output)
    font_rel_path = copy_assets(font_path, output_path.parent)
    
    # Batch fetch altitudes for all steps
    locations = [(step.location.lat, step.location.lon) for step in steps]
    elevations = get_altitude_batch(locations)
    
    # Prepare template environment
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("album.html")
    
    # Prepare step data with elevations
    step_data_list = []
    for step, elevation in zip(steps, elevations):
        image_path = step_images.get(step.id) if step.id else None
        step_data = prepare_step_data(step, image_path, trip_data)
        # Update altitude with fetched value
        step_data["altitude_str"] = format_altitude(elevation)
        step_data_list.append(step_data)
    
    # Render template
    html = template.render(
        steps=step_data_list,
        font_path=font_rel_path,
    )
    
    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return output_path

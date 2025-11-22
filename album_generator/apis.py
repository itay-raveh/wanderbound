"""External API integrations for altitude, country maps, and flags."""

import requests
from typing import Optional, Any, Tuple, List, Iterator
import time
import json
import base64
from pathlib import Path
from PIL import Image
import io
from pyproj import Geod

try:
    import geopandas as gpd
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    from matplotlib.collections import PatchCollection

    HAS_GEO = True
except ImportError:
    HAS_GEO = False


CACHE_DIR = Path.home() / ".polarsteps_album_cache"
CACHE_DIR.mkdir(exist_ok=True)

_COUNTRY_BOUNDS = None
_COUNTRY_COLORS = {}
_SVG_VIEWBOXES = {}
_SVG_PATH_BOUNDS = {}
_SVG_TRANSFORMS = {}
_GEOD = Geod(ellps="WGS84")


def _load_country_bounds() -> dict:
    """Load country bounds from JSON file (fallback)."""
    global _COUNTRY_BOUNDS
    if _COUNTRY_BOUNDS is None:
        bounds_file = Path(__file__).parent / "country_bounding_boxes.json"
        with open(bounds_file, "r") as f:
            _COUNTRY_BOUNDS = json.load(f)
    return _COUNTRY_BOUNDS


def get_cached(key: str) -> Optional[Any]:
    """Get cached API response."""
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                if time.time() - data.get("timestamp", 0) < 86400:
                    return data.get("value")
        except Exception:
            pass
    return None


def set_cached(key: str, value: Any):
    """Cache API response."""
    cache_file = CACHE_DIR / f"{key}.json"
    try:
        with open(cache_file, "w") as f:
            json.dump({"timestamp": time.time(), "value": value}, f)
    except Exception:
        pass


def _chunks(lst: List[Any], n: int) -> Iterator[List[Any]]:
    """Split list into chunks of size n."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def _load_elevation_cache(cache_file: Path) -> dict[str, Optional[float]]:
    """Load elevation cache from file."""
    if cache_file.exists():
        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ Error loading elevation cache: {e}")
    return {}


def _save_elevation_cache(cache_file: Path, cache: dict[str, Optional[float]]):
    """Save elevation cache to file."""
    try:
        with open(cache_file, "w") as f:
            json.dump(cache, f)
    except IOError as e:
        print(f"⚠️ Error saving elevation cache: {e}")


def get_altitude_batch(locations: List[Tuple[float, float]]) -> List[Optional[float]]:
    """Get altitude for multiple coordinates using OpenTopoData API with batching."""
    cache_file = CACHE_DIR / "elevation_cache.json"

    # Load cache
    cache = _load_elevation_cache(cache_file)

    all_elevations: List[Optional[float]] = []
    locations_to_query: List[Tuple[float, float]] = []

    for loc in locations:
        lat, lon = loc
        key = f"{lat},{lon}"
        if key in cache:
            all_elevations.append(cache[key])
        else:
            locations_to_query.append(loc)

    max_locations_per_request = 100
    max_calls_per_day = 1000
    calls_made = 0

    for batch in _chunks(locations_to_query, max_locations_per_request):
        if calls_made >= max_calls_per_day:
            print("⚠️ Reached maximum API calls for today. Using cached data only.")
            all_elevations.extend([None] * len(batch))
            continue

        locations_param = "|".join([f"{lat},{lon}" for lat, lon in batch])
        url = f"https://api.opentopodata.org/v1/aster30m?locations={locations_param}"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if "results" in data:
                for loc, result in zip(batch, data["results"]):
                    lat, lon = loc
                    elevation = result.get("elevation")
                    all_elevations.append(elevation)

                    key = f"{lat},{lon}"
                    cache[key] = elevation
            else:
                all_elevations.extend([None] * len(batch))

            calls_made += 1
            time.sleep(1)

        except requests.exceptions.RequestException as e:
            print(f"⚠️ Failed to get elevation for batch: {e}")
            all_elevations.extend([None] * len(batch))
        except (KeyError, ValueError) as e:
            print(f"⚠️ Error parsing elevation response: {e}")
            all_elevations.extend([None] * len(batch))

    _save_elevation_cache(cache_file, cache)

    return all_elevations


def get_altitude(lat: float, lon: float) -> Optional[float]:
    """
    Get altitude for a single coordinate.
    Uses batch API internally for efficiency.
    """
    results = get_altitude_batch([(lat, lon)])
    return results[0] if results else None


def get_country_flag_data_uri(country_code: str) -> Optional[str]:
    """
    Get country flag image as data URI.
    Uses flagcdn.com.
    """
    if not country_code:
        return None

    cache_key = f"flag_{country_code.lower()}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        url = f"https://flagcdn.com/w40/{country_code.lower()}.png"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        if response.status_code == 200:
            image_data = base64.b64encode(response.content).decode("utf-8")
            data_uri = f"data:image/png;base64,{image_data}"
            set_cached(cache_key, data_uri)
            return data_uri
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Failed to get flag for {country_code}: {e}")
    except Exception as e:
        print(f"⚠️ Error processing flag for {country_code}: {e}")

    return None


def _color_distance(color1: str, color2: str) -> float:
    """Calculate color distance (0-1 scale, 0 = identical)."""
    if not color1.startswith("#") or not color2.startswith("#"):
        return 1.0

    r1 = int(color1[1:3], 16)
    g1 = int(color1[3:5], 16)
    b1 = int(color1[5:7], 16)
    r2 = int(color2[1:3], 16)
    g2 = int(color2[3:5], 16)
    b2 = int(color2[5:7], 16)

    dist = ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5
    return dist / (255 * (3**0.5))


def _get_color_brightness(color: str) -> float:
    """Calculate relative luminance/brightness of a color (0-1, 0 = black, 1 = white)."""
    if not color or not color.startswith("#"):
        return 0.5

    r = int(color[1:3], 16) / 255.0
    g = int(color[3:5], 16) / 255.0
    b = int(color[5:7], 16) / 255.0

    r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4

    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _adjust_color_for_contrast(color: str, light_mode: bool) -> str:
    """Adjust color brightness to ensure good contrast with text.
    In dark mode: ensure color is dark enough (brightness < 0.5)
    In light mode: ensure color is light enough (brightness > 0.5)"""
    if not color or not color.startswith("#"):
        return color

    brightness = _get_color_brightness(color)
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)

    if light_mode:
        target_brightness = 0.55
        if brightness < target_brightness:
            blend_factor = (
                (target_brightness - brightness) / (1.0 - brightness)
                if brightness < 1.0
                else 0
            )
            blend_factor = min(0.25, blend_factor)
            r = int(r + (255 - r) * blend_factor)
            g = int(g + (255 - g) * blend_factor)
            b = int(b + (255 - b) * blend_factor)
    else:
        target_brightness = 0.45
        if brightness > target_brightness:
            blend_factor = (
                (brightness - target_brightness) / brightness if brightness > 0 else 0
            )
            blend_factor = min(0.25, blend_factor)
            r = int(r * (1 - blend_factor))
            g = int(g * (1 - blend_factor))
            b = int(b * (1 - blend_factor))

    return (
        f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"
    )


def _nudge_color_to_avoid_conflict(color: str, country_code: str) -> str:
    """Nudge a color to avoid conflicts with other countries.
    Preserves the color family (red stays red, blue stays blue, etc.)"""
    if not color or not color.startswith("#"):
        return color

    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)

    conflict_threshold = 0.10
    for other_code, other_color in _COUNTRY_COLORS.items():
        if other_code != country_code:
            dist = _color_distance(color, other_color)
            if dist < conflict_threshold:
                import hashlib

                hash_val = int(hashlib.md5(country_code.encode()).hexdigest(), 16)

                dominant = max(r, g, b)
                if dominant == r and r > g + 20 and r > b + 20:
                    r = max(0, min(255, r + ((hash_val % 16) - 8)))
                    g = max(0, min(255, g + ((hash_val % 6) - 3)))
                    b = max(0, min(255, b + ((hash_val % 6) - 3)))
                elif dominant == g and g > r + 20 and g > b + 20:
                    g = max(0, min(255, g + ((hash_val % 16) - 8)))
                    r = max(0, min(255, r + ((hash_val % 6) - 3)))
                    b = max(0, min(255, b + ((hash_val % 6) - 3)))
                elif dominant == b and b > r + 20 and b > g + 20:
                    b = max(0, min(255, b + ((hash_val % 16) - 8)))
                    r = max(0, min(255, r + ((hash_val % 6) - 3)))
                    g = max(0, min(255, g + ((hash_val % 6) - 3)))
                else:
                    r = max(0, min(255, r + ((hash_val % 10) - 5)))
                    g = max(0, min(255, g + (((hash_val >> 8) % 10) - 5)))
                    b = max(0, min(255, b + (((hash_val >> 16) % 10) - 5)))

                color = f"#{r:02x}{g:02x}{b:02x}"
                break

    return color


def extract_prominent_color_from_flag(
    flag_data_uri: Optional[str],
    country_code: Optional[str] = None,
    light_mode: bool = False,
) -> str:
    """Extract the most common non-white/black color from a country flag image.
    If the most common color conflicts with an existing country, tries the second most common, etc.
    Adjusts color brightness to ensure good contrast with text."""
    if not flag_data_uri:
        return "#ff69b4"

    try:
        if not flag_data_uri.startswith("data:image"):
            return "#ff69b4"

        base64_data = flag_data_uri.split(",")[1]
        image_bytes = base64.b64decode(base64_data)
        image = Image.open(io.BytesIO(image_bytes))

        if image.mode != "RGB":
            image = image.convert("RGB")

        pixels = list(image.getdata())  # type: ignore

        from collections import Counter

        filtered_pixels = []
        for r, g, b in pixels:
            brightness = (r + g + b) / 3
            if brightness > 240 or brightness < 15:
                continue
            filtered_pixels.append((r, g, b))

        if not filtered_pixels:
            return "#ff69b4"

        # Get multiple most common colors with their counts
        color_counts = Counter(filtered_pixels).most_common(5)
        if not color_counts:
            return "#ff69b4"

        total_pixels = len(filtered_pixels)
        most_common_count = color_counts[0][1]

        # Try each candidate color, starting with most common
        for color_tuple, count in color_counts:
            # Only consider colors that are at least 30% as common as the most common
            # This ensures we don't pick a rare color
            if count < most_common_count * 0.3:
                break

            r, g, b = color_tuple
            candidate_color = f"#{r:02x}{g:02x}{b:02x}"

            # Check if this color conflicts with existing countries
            if country_code:
                has_conflict = False
                conflict_threshold = 0.10
                for other_code, other_color in _COUNTRY_COLORS.items():
                    if other_code != country_code.lower():
                        dist = _color_distance(candidate_color, other_color)
                        if dist < conflict_threshold:
                            has_conflict = True
                            break

                # If no conflict, use this color
                if not has_conflict:
                    color = _adjust_color_for_contrast(candidate_color, light_mode)
                    _COUNTRY_COLORS[country_code.lower()] = color
                    return color
            else:
                # No country code, adjust and return the most common
                color = _adjust_color_for_contrast(candidate_color, light_mode)
                return color

        # All candidates conflict - use the most common and nudge it
        r, g, b = color_counts[0][0]
        color = f"#{r:02x}{g:02x}{b:02x}"

        if country_code:
            color = _nudge_color_to_avoid_conflict(color, country_code.lower())

        # Adjust for contrast
        color = _adjust_color_for_contrast(color, light_mode)

        if country_code:
            _COUNTRY_COLORS[country_code.lower()] = color

        return color

    except Exception as e:
        print(f"⚠️ Error extracting color from flag: {e}")
        return "#ff69b4"


def _generate_geo_calibrated_svg(
    country_code: str, width: int = 1024, height: int = 1024
) -> Optional[str]:
    """
    Generate a geo-calibrated SVG map of a country using geopandas and Natural Earth Data.
    Returns SVG string with embedded geographic bounds in the viewBox.
    """
    if not HAS_GEO:
        return None

    country_code_lower = country_code.lower()

    try:
        # Use Natural Earth 50m data (good balance between quality and file size)
        ne_50m_url = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
        cache_key_data = "ne_50m_admin_0_countries"

        # Try to load from cache first
        cache_file = CACHE_DIR / f"{cache_key_data}.geojson"
        if cache_file.exists():
            try:
                world = gpd.read_file(str(cache_file))
            except:
                world = None
        else:
            world = None

        if world is None:
            # Download and cache
            try:
                print(f"Downloading Natural Earth 50m data for {country_code}...")
                world = gpd.read_file(ne_50m_url)
                # Cache it
                world.to_file(str(cache_file), driver="GeoJSON")
            except Exception as e:
                print(f"⚠️ Failed to download Natural Earth 50m data: {e}")
                return None

        # Map country codes to Natural Earth country names (uses 'ADMIN' field)
        country_names = {
            "cl": "Chile",
            "ar": "Argentina",
            "pe": "Peru",
            "bo": "Bolivia",
            "br": "Brazil",
            "us": "United States of America",
            "ca": "Canada",
            "mx": "Mexico",
            "co": "Colombia",
            "ec": "Ecuador",
            "uy": "Uruguay",
            "py": "Paraguay",
            "ve": "Venezuela",
            "gy": "Guyana",
            "sr": "Suriname",
            "gf": "French Guiana",
            "fk": "Falkland Islands",
        }
        country_name = country_names.get(country_code_lower)

        if not country_name:
            return None

        # Filter by ADMIN field (Natural Earth uses 'ADMIN' for country names)
        country_gdf = world[world["ADMIN"] == country_name]

        if country_gdf.empty:
            # Fallback: try case-insensitive search
            country_gdf = world[
                world["ADMIN"].str.contains(country_name, case=False, na=False)
            ]

        if country_gdf.empty:
            return None

        # Use the first match
        gdf = country_gdf.iloc[[0]]

        # Get bounds in geographic coordinates (WGS84)
        bounds = gdf.total_bounds  # [minx, miny, maxx, maxy] in lat/lon
        min_lon, min_lat, max_lon, max_lat = bounds[0], bounds[1], bounds[2], bounds[3]

        # Use UTM projection for better accuracy (less distortion)
        local_crs = gdf.estimate_utm_crs()
        gdf_proj = gdf.to_crs(local_crs)
        bounds_proj = gdf_proj.total_bounds

        # Create figure with higher resolution
        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        ax.set_xlim(bounds_proj[0], bounds_proj[2])
        ax.set_ylim(bounds_proj[1], bounds_proj[3])
        ax.set_aspect("equal")
        ax.axis("off")

        # Plot the country
        gdf_proj.plot(ax=ax, color="white", edgecolor="none", linewidth=0)

        # Get the actual bounds of what was plotted (after aspect ratio and limits)
        # This accounts for any adjustments matplotlib makes
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        actual_bounds = [xlim[0], ylim[0], xlim[1], ylim[1]]

        # Save to SVG
        from io import StringIO

        svg_buffer = StringIO()
        fig.savefig(
            svg_buffer,
            format="svg",
            bbox_inches="tight",
            pad_inches=0,
            transparent=True,
        )
        svg_data = svg_buffer.getvalue()
        plt.close(fig)

        # Extract viewBox and add geographic bounds + CRS info
        import re

        viewbox_match = re.search(r'viewBox="([^"]+)"', svg_data)
        if viewbox_match:
            viewbox = viewbox_match.group(1)
            # Extract the actual viewBox values for CRS storage
            viewbox_vals = [float(x) for x in viewbox_match.group(1).split()]
        else:
            viewbox = "0 0 100 100"
            viewbox_vals = [0, 0, 100, 100]

        # Store geographic bounds and projected bounds (actual coordinate bounds, not viewBox) + CRS
        geo_bounds_attr = f'data-geo-bounds="{min_lon},{min_lat},{max_lon},{max_lat}"'
        # Store the actual plotted bounds (from ax.get_xlim/ylim) which may differ slightly
        # from bounds_proj due to aspect ratio adjustments
        proj_bounds_attr = f'data-proj-bounds="{actual_bounds[0]},{actual_bounds[1]},{actual_bounds[2]},{actual_bounds[3]}"'
        crs_attr = f'data-crs="{local_crs.to_string()}"'
        svg_data = re.sub(
            r"<svg([^>]*)>",
            f"<svg\\1 {geo_bounds_attr} {proj_bounds_attr} {crs_attr}>",
            svg_data,
            count=1,
        )

        # Ensure white fill
        svg_data = re.sub(r'fill="[^"]*"', 'fill="#ffffff"', svg_data)
        # Add fill to paths that don't have it
        svg_data = re.sub(
            r"<path([^>]*?)(?:\s|>)(?!.*fill=)", r'<path\1 fill="#ffffff"', svg_data
        )

        # Remove XML declaration and DOCTYPE for HTML embedding
        svg_data = re.sub(r"<\?xml[^>]*\?>", "", svg_data)
        svg_data = re.sub(r"<!DOCTYPE[^>]*>", "", svg_data)

        return svg_data

    except Exception as e:
        print(f"⚠️ Error generating geo-calibrated SVG for {country_code}: {e}")
        return None


def get_country_map_svg(
    country_code: str, lat: Optional[float] = None, lon: Optional[float] = None
) -> Optional[str]:
    """Get country map/silhouette as raw SVG string."""
    if not country_code:
        return None

    cache_key_svg = f"map_svg_{country_code.lower()}"
    cached_svg = get_cached(cache_key_svg)
    if cached_svg is not None:
        return cached_svg

    # Try to generate geo-calibrated SVG first
    if HAS_GEO:
        svg_data = _generate_geo_calibrated_svg(country_code)
        if svg_data:
            set_cached(cache_key_svg, svg_data)
            return svg_data

    # Fallback to mapsicon (not geo-calibrated)
    svg_url = f"https://raw.githubusercontent.com/djaiss/mapsicon/master/all/{country_code.lower()}/vector.svg"

    try:
        response = requests.get(svg_url, timeout=10)
        response.raise_for_status()
        if response.status_code == 200:
            svg_data = response.text
            import re

            # Extract and cache viewBox
            viewbox_match = re.search(r'viewBox="([^"]+)"', svg_data)
            if viewbox_match:
                viewbox_str = viewbox_match.group(1)
                viewbox = [float(x) for x in viewbox_str.split()]
                if len(viewbox) == 4:
                    _SVG_VIEWBOXES[country_code.lower()] = viewbox

            # Extract transform from SVG
            # Typical format: transform="translate(0.000000,1024.000000) scale(0.100000,-0.100000)"
            transform_match = re.search(r'transform="([^"]+)"', svg_data)
            if transform_match:
                transform_str = transform_match.group(1)
                # Parse translate and scale
                translate_match = re.search(r"translate\(([^)]+)\)", transform_str)
                scale_match = re.search(r"scale\(([^)]+)\)", transform_str)

                translate_x, translate_y = 0, 0
                scale_x, scale_y = 1, 1

                if translate_match:
                    translate_parts = [
                        float(x.strip()) for x in translate_match.group(1).split(",")
                    ]
                    if len(translate_parts) >= 2:
                        translate_x, translate_y = (
                            translate_parts[0],
                            translate_parts[1],
                        )

                if scale_match:
                    scale_parts = [
                        float(x.strip()) for x in scale_match.group(1).split(",")
                    ]
                    if len(scale_parts) >= 2:
                        scale_x, scale_y = scale_parts[0], scale_parts[1]
                    elif len(scale_parts) == 1:
                        scale_x = scale_y = scale_parts[0]

                _SVG_TRANSFORMS[country_code.lower()] = {
                    "translate_x": translate_x,
                    "translate_y": translate_y,
                    "scale_x": scale_x,
                    "scale_y": scale_y,
                }

            # Extract actual path bounds from SVG
            # The SVG has transforms, so we need to extract the actual coordinate bounds
            paths = re.findall(r'<path[^>]*d="([^"]+)"', svg_data)
            if paths:
                # Extract all numeric coordinates from path data
                # Path format: M x y L x y ... or M x,y L x,y ...
                all_x = []
                all_y = []
                for path_d in paths:
                    # Match coordinates (numbers, possibly negative, possibly decimal)
                    numbers = re.findall(r"-?\d+\.?\d*", path_d)
                    # Path commands alternate or come in pairs
                    # For simplicity, extract all numbers and assume they're x,y pairs
                    for i, num_str in enumerate(numbers):
                        try:
                            num = float(num_str)
                            if i % 2 == 0:  # Even indices are x
                                all_x.append(num)
                            else:  # Odd indices are y
                                all_y.append(num)
                        except ValueError:
                            continue

                if all_x and all_y:
                    # Store the actual path bounds (before transform)
                    path_bounds = {
                        "min_x": min(all_x),
                        "max_x": max(all_x),
                        "min_y": min(all_y),
                        "max_y": max(all_y),
                    }
                    _SVG_PATH_BOUNDS[country_code.lower()] = path_bounds

                    # Also calculate the rendered bounds (after transform) to see actual country size
                    transform = _SVG_TRANSFORMS.get(country_code.lower())
                    if transform and viewbox:
                        scale_x = transform["scale_x"]
                        scale_y = transform["scale_y"]
                        translate_x = transform["translate_x"]
                        translate_y = transform["translate_y"]

                        # Apply transform to get rendered bounds
                        rendered_min_x = path_bounds["min_x"] * scale_x + translate_x
                        rendered_max_x = path_bounds["max_x"] * scale_x + translate_x
                        rendered_min_y = path_bounds["min_y"] * scale_y + translate_y
                        rendered_max_y = path_bounds["max_y"] * scale_y + translate_y

                        # Store rendered bounds for positioning
                        _SVG_PATH_BOUNDS[country_code.lower()]["rendered"] = {
                            "min_x": rendered_min_x,
                            "max_x": rendered_max_x,
                            "min_y": rendered_min_y,
                            "max_y": rendered_max_y,
                        }

            svg_data = re.sub(r'fill="#000000"', 'fill="#ffffff"', svg_data)
            # Remove XML declaration and DOCTYPE for HTML embedding
            svg_data = re.sub(r"<\?xml[^>]*\?>", "", svg_data)
            svg_data = re.sub(r"<!DOCTYPE[^>]*>", "", svg_data)
            set_cached(cache_key_svg, svg_data)
            return svg_data
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Failed to get map for {country_code}: {e}")
    except Exception as e:
        print(f"⚠️ Error processing map for {country_code}: {e}")

    return None


def get_country_map_data_uri(
    country_code: str, lat: Optional[float] = None, lon: Optional[float] = None
) -> Optional[str]:
    """Get country map/silhouette image as data URI with proper geographic coordinates."""
    if not country_code:
        return None

    cache_key = f"map_{country_code.lower()}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    # Get raw SVG and encode it
    svg_data = get_country_map_svg(country_code, lat, lon)
    if svg_data:
        svg_encoded = base64.b64encode(svg_data.encode("utf-8")).decode("utf-8")
        data_uri = f"data:image/svg+xml;base64,{svg_encoded}"
        set_cached(cache_key, data_uri)
        return data_uri

    return None

    # Fallback to mapsicon (not geo-calibrated)
    svg_url = f"https://raw.githubusercontent.com/djaiss/mapsicon/master/all/{country_code.lower()}/vector.svg"

    try:
        response = requests.get(svg_url, timeout=10)
        response.raise_for_status()
        if response.status_code == 200:
            svg_data = response.text
            import re

            # Extract and cache viewBox
            viewbox_match = re.search(r'viewBox="([^"]+)"', svg_data)
            if viewbox_match:
                viewbox_str = viewbox_match.group(1)
                viewbox = [float(x) for x in viewbox_str.split()]
                if len(viewbox) == 4:
                    _SVG_VIEWBOXES[country_code.lower()] = viewbox

            # Extract transform from SVG
            # Typical format: transform="translate(0.000000,1024.000000) scale(0.100000,-0.100000)"
            transform_match = re.search(r'transform="([^"]+)"', svg_data)
            if transform_match:
                transform_str = transform_match.group(1)
                # Parse translate and scale
                translate_match = re.search(r"translate\(([^)]+)\)", transform_str)
                scale_match = re.search(r"scale\(([^)]+)\)", transform_str)

                translate_x, translate_y = 0, 0
                scale_x, scale_y = 1, 1

                if translate_match:
                    translate_parts = [
                        float(x.strip()) for x in translate_match.group(1).split(",")
                    ]
                    if len(translate_parts) >= 2:
                        translate_x, translate_y = (
                            translate_parts[0],
                            translate_parts[1],
                        )

                if scale_match:
                    scale_parts = [
                        float(x.strip()) for x in scale_match.group(1).split(",")
                    ]
                    if len(scale_parts) >= 2:
                        scale_x, scale_y = scale_parts[0], scale_parts[1]
                    elif len(scale_parts) == 1:
                        scale_x = scale_y = scale_parts[0]

                _SVG_TRANSFORMS[country_code.lower()] = {
                    "translate_x": translate_x,
                    "translate_y": translate_y,
                    "scale_x": scale_x,
                    "scale_y": scale_y,
                }

            # Extract actual path bounds from SVG
            # The SVG has transforms, so we need to extract the actual coordinate bounds
            paths = re.findall(r'<path[^>]*d="([^"]+)"', svg_data)
            if paths:
                # Extract all numeric coordinates from path data
                # Path format: M x y L x y ... or M x,y L x,y ...
                all_x = []
                all_y = []
                for path_d in paths:
                    # Match coordinates (numbers, possibly negative, possibly decimal)
                    numbers = re.findall(r"-?\d+\.?\d*", path_d)
                    # Path commands alternate or come in pairs
                    # For simplicity, extract all numbers and assume they're x,y pairs
                    for i, num_str in enumerate(numbers):
                        try:
                            num = float(num_str)
                            if i % 2 == 0:  # Even indices are x
                                all_x.append(num)
                            else:  # Odd indices are y
                                all_y.append(num)
                        except ValueError:
                            continue

                if all_x and all_y:
                    # Store the actual path bounds (before transform)
                    path_bounds = {
                        "min_x": min(all_x),
                        "max_x": max(all_x),
                        "min_y": min(all_y),
                        "max_y": max(all_y),
                    }
                    _SVG_PATH_BOUNDS[country_code.lower()] = path_bounds

                    # Also calculate the rendered bounds (after transform) to see actual country size
                    transform = _SVG_TRANSFORMS.get(country_code.lower())
                    if transform and viewbox:
                        scale_x = transform["scale_x"]
                        scale_y = transform["scale_y"]
                        translate_x = transform["translate_x"]
                        translate_y = transform["translate_y"]

                        # Apply transform to get rendered bounds
                        rendered_min_x = path_bounds["min_x"] * scale_x + translate_x
                        rendered_max_x = path_bounds["max_x"] * scale_x + translate_x
                        rendered_min_y = path_bounds["min_y"] * scale_y + translate_y
                        rendered_max_y = path_bounds["max_y"] * scale_y + translate_y

                        # Store rendered bounds for positioning
                        _SVG_PATH_BOUNDS[country_code.lower()]["rendered"] = {
                            "min_x": rendered_min_x,
                            "max_x": rendered_max_x,
                            "min_y": rendered_min_y,
                            "max_y": rendered_max_y,
                        }

            svg_data = re.sub(r'fill="#000000"', 'fill="#ffffff"', svg_data)
            svg_encoded = base64.b64encode(svg_data.encode("utf-8")).decode("utf-8")
            data_uri = f"data:image/svg+xml;base64,{svg_encoded}"
            set_cached(cache_key, data_uri)
            return data_uri
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Failed to get map for {country_code}: {e}")
    except Exception as e:
        print(f"⚠️ Error processing map for {country_code}: {e}")

    return None


def get_country_map_dot_position(
    country_code: str, lat: float, lon: float
) -> Optional[Tuple[float, float]]:
    """
    Calculate the relative position (0-100%) of a location dot within a country map.

    For geo-calibrated SVGs (generated from Natural Earth Data), we use the embedded
    geographic bounds to map lat/lon directly to SVG coordinates.

    For mapsicon SVGs (not geo-calibrated), we fall back to bounding box mapping.

    Returns (x_percent, y_percent) where 0,0 is top-left and 100,100 is bottom-right.
    """
    country_code_lower = country_code.lower()

    if not country_code:
        return (50.0, 50.0)

    # Get raw SVG (preferred method)
    svg_data = get_country_map_svg(country_code_lower)

    # Check if SVG has geographic bounds (geo-calibrated)
    if svg_data:

        # Check for geo-calibrated bounds
        import re

        geo_bounds_match = re.search(r'data-geo-bounds="([^"]+)"', svg_data)
        if geo_bounds_match:
            # This is a geo-calibrated SVG - use the embedded bounds
            bounds_str = geo_bounds_match.group(1)
            bounds = [float(x) for x in bounds_str.split(",")]
            if len(bounds) == 4:
                min_lon, min_lat, max_lon, max_lat = bounds

                # Extract viewBox and CRS from SVG
                viewbox_match = re.search(r'viewBox="([^"]+)"', svg_data)
                proj_bounds_match = re.search(r'data-proj-bounds="([^"]+)"', svg_data)
                crs_match = re.search(r'data-crs="([^"]+)"', svg_data)

                if viewbox_match and proj_bounds_match and crs_match:
                    viewbox = [float(x) for x in viewbox_match.group(1).split()]
                    proj_bounds = [
                        float(x) for x in proj_bounds_match.group(1).split(",")
                    ]
                    crs_str = crs_match.group(1)

                    if len(viewbox) == 4 and len(proj_bounds) == 4:
                        from shapely.geometry import Point

                        point_geo = gpd.GeoDataFrame(
                            geometry=[Point(lon, lat)], crs="EPSG:4326"
                        )
                        point_proj = point_geo.to_crs(crs_str)

                        proj_x = point_proj.geometry.iloc[0].x
                        proj_y = point_proj.geometry.iloc[0].y

                        proj_min_x, proj_min_y, proj_max_x, proj_max_y = proj_bounds
                        proj_width = proj_max_x - proj_min_x
                        proj_height = proj_max_y - proj_min_y

                        x_ratio = (proj_x - proj_min_x) / proj_width
                        y_ratio = (proj_max_y - proj_y) / proj_height

                        viewbox_width = viewbox[2]
                        viewbox_height = viewbox[3]

                        x_percent = x_ratio * 100
                        y_percent = y_ratio * 100

                        x_percent = max(0, min(100, x_percent))
                        y_percent = max(0, min(100, y_percent))

                        return (x_percent, y_percent)

                if viewbox_match:
                    viewbox = [float(x) for x in viewbox_match.group(1).split()]
                    if len(viewbox) == 4:
                        viewbox_min_lon = viewbox[0]
                        viewbox_min_lat = viewbox[1]
                        viewbox_width = viewbox[2]
                        viewbox_height = viewbox[3]

                        x_percent = ((lon - viewbox_min_lon) / viewbox_width) * 100
                        y_percent = ((max_lat - lat) / abs(viewbox_height)) * 100

                        x_percent = max(0, min(100, x_percent))
                        y_percent = max(0, min(100, y_percent))

                        return (x_percent, y_percent)

    rendered_bounds = _SVG_PATH_BOUNDS.get(country_code_lower, {}).get("rendered")
    viewbox = _SVG_VIEWBOXES.get(country_code_lower)

    if rendered_bounds and viewbox and len(viewbox) == 4:
        country_bounds = _load_country_bounds()
        if country_code_lower in country_bounds:
            bbox = country_bounds[country_code_lower]
            if "sw" in bbox and "ne" in bbox:
                sw = bbox["sw"]
                ne = bbox["ne"]

                lat_range = ne["lat"] - sw["lat"]
                lon_range = ne["lon"] - sw["lon"]

                if lat_range > 0 and lon_range > 0:
                    geo_x = (lon - sw["lon"]) / lon_range
                    geo_y = (ne["lat"] - lat) / lat_range

                    rendered_x = rendered_bounds["min_x"] + geo_x * (
                        rendered_bounds["max_x"] - rendered_bounds["min_x"]
                    )
                    rendered_y = rendered_bounds["min_y"] + geo_y * (
                        rendered_bounds["max_y"] - rendered_bounds["min_y"]
                    )

                    viewbox_width = viewbox[2] - viewbox[0]
                    viewbox_height = viewbox[3] - viewbox[1]

                    x_percent = ((rendered_x - viewbox[0]) / viewbox_width) * 100
                    y_percent = ((rendered_y - viewbox[1]) / viewbox_height) * 100

                    x_percent = max(0, min(100, x_percent))
                    y_percent = max(0, min(100, y_percent))

                    return (x_percent, y_percent)

    country_bounds = _load_country_bounds()
    if country_code_lower not in country_bounds:
        return (50.0, 50.0)

    bounding_box = country_bounds[country_code_lower]

    if "sw" in bounding_box and "ne" in bounding_box:
        sw = bounding_box["sw"]
        ne = bounding_box["ne"]

        # Use simple equirectangular projection (linear interpolation)
        lat_range = ne["lat"] - sw["lat"]
        lon_range = ne["lon"] - sw["lon"]

        if lat_range == 0 or lon_range == 0:
            return (50.0, 50.0)

        lon_percentage = ((lon - sw["lon"]) / lon_range) * 100
        lat_percentage = ((ne["lat"] - lat) / lat_range) * 100

        lon_percentage = max(5, min(95, lon_percentage))
        lat_percentage = max(5, min(95, lat_percentage))

        return (lon_percentage, lat_percentage)
    else:
        return (50.0, 50.0)


def format_altitude(altitude: Optional[float]) -> str:
    """Format altitude in meters with proper formatting."""
    if altitude is None:
        return "N/A"

    # Round to nearest meter
    meters = int(round(altitude))
    return f"{meters:,}"

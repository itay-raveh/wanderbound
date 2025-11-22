"""External API integrations for altitude, country maps, and flags."""

import requests
from typing import Optional, Any, Tuple, List, Iterator
import time
import json
import base64
from pathlib import Path
from PIL import Image
import io


CACHE_DIR = Path.home() / ".polarsteps_album_cache"
CACHE_DIR.mkdir(exist_ok=True)

_COUNTRY_BOUNDS = None


def _load_country_bounds() -> dict:
    """Load country bounds from JSON file."""
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
                # Check if cache is less than 24 hours old
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

    # First, check cache
    for loc in locations:
        lat, lon = loc
        key = f"{lat},{lon}"
        if key in cache:
            all_elevations.append(cache[key])
        else:
            locations_to_query.append(loc)

    # Process locations not in cache
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

                    # Cache the result
                    key = f"{lat},{lon}"
                    cache[key] = elevation
            else:
                all_elevations.extend([None] * len(batch))

            calls_made += 1
            time.sleep(1)  # Rate limit: 1 call per second

        except requests.exceptions.RequestException as e:
            print(f"⚠️ Failed to get elevation for batch: {e}")
            all_elevations.extend([None] * len(batch))
        except (KeyError, ValueError) as e:
            print(f"⚠️ Error parsing elevation response: {e}")
            all_elevations.extend([None] * len(batch))

    # Save cache
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


def extract_prominent_color_from_flag(flag_data_uri: Optional[str]) -> str:
    """Extract the most prominent color from a country flag image."""
    if not flag_data_uri:
        return "#ff69b4"  # Default pink

    try:
        # Extract base64 data from data URI
        if not flag_data_uri.startswith("data:image"):
            return "#ff69b4"

        base64_data = flag_data_uri.split(",")[1]
        image_bytes = base64.b64decode(base64_data)
        image = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if needed
        if image.mode != "RGB":
            image = image.convert("RGB")

        pixels = list(image.getdata())  # type: ignore

        color_scores = []

        for r, g, b in pixels:
            brightness = (r + g + b) / 3
            if brightness > 240 or brightness < 15:
                continue

            max_val = max(r, g, b)
            min_val = min(r, g, b)
            if max_val == 0:
                continue

            saturation = (max_val - min_val) / max_val if max_val > 0 else 0

            if 50 < brightness < 200 and saturation > 0.2:
                brightness_score = brightness / 255
                saturation_score = 1 - (saturation * 0.5)
                score = brightness_score * 0.7 + saturation_score * 0.3
                color_scores.append((score, (r, g, b)))

        if not color_scores:
            from collections import Counter
            filtered_pixels = [
                (r, g, b) for r, g, b in pixels if 50 < (r + g + b) / 3 < 200
            ]
            if filtered_pixels:
                most_common = Counter(filtered_pixels).most_common(1)[0][0]
                r, g, b = most_common
                return f"#{r:02x}{g:02x}{b:02x}"
            return "#ff69b4"

        color_scores.sort(reverse=True, key=lambda x: x[0])
        best_color = color_scores[0][1]
        r, g, b = best_color
        return f"#{r:02x}{g:02x}{b:02x}"

    except Exception as e:
        print(f"⚠️ Error extracting color from flag: {e}")
        return "#ff69b4"  # Default pink


def get_country_map_data_uri(
    country_code: str, lat: Optional[float] = None, lon: Optional[float] = None
) -> Optional[str]:
    """Get country map/silhouette image as data URI."""
    if not country_code:
        return None

    cache_key = f"map_{country_code.lower()}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    svg_url = f"https://raw.githubusercontent.com/djaiss/mapsicon/master/all/{country_code.lower()}/vector.svg"

    try:
        response = requests.get(svg_url, timeout=10)
        response.raise_for_status()
        if response.status_code == 200:
            svg_data = response.text
            import re
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
    Returns (x_percent, y_percent) where 0,0 is top-left and 100,100 is bottom-right.
    """
    country_bounds = _load_country_bounds()
    country_code_lower = country_code.lower()

    if not country_code or country_code_lower not in country_bounds:
        return (50.0, 50.0)

    bounding_box = country_bounds[country_code_lower]

    if "sw" in bounding_box and "ne" in bounding_box:
        sw = bounding_box["sw"]
        ne = bounding_box["ne"]

        # Simple linear interpolation
        lat_range = ne["lat"] - sw["lat"]
        lon_range = ne["lon"] - sw["lon"]

        if lat_range == 0 or lon_range == 0:
            return (50.0, 50.0)

        x_percent = ((lon - sw["lon"]) / lon_range) * 100
        y_percent = ((ne["lat"] - lat) / lat_range) * 100
        
        x_percent = x_percent - 7
        y_percent = y_percent + 15

        # Clamp to 5-95% to keep dot visible
        x_percent = max(5, min(95, x_percent))
        y_percent = max(5, min(95, y_percent))

        return (x_percent, y_percent)
    else:
        return (50.0, 50.0)


def format_altitude(altitude: Optional[float]) -> str:
    """Format altitude in meters with proper formatting."""
    if altitude is None:
        return "N/A"

    # Round to nearest meter
    meters = int(round(altitude))
    return f"{meters:,}"

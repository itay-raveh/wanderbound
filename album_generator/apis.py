"""External API integrations for altitude, country maps, and flags."""
import requests
from typing import Optional, Any, Tuple, List, Iterator
import time
import json
import base64
from pathlib import Path
from pyproj import Geod


# Cache directory for API responses
CACHE_DIR = Path.home() / ".polarsteps_album_cache"
CACHE_DIR.mkdir(exist_ok=True)

# Load country bounds from JSON file
_COUNTRY_BOUNDS = None
_GEOD = Geod(ellps="WGS84")


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


def get_altitude_batch(locations: List[Tuple[float, float]]) -> List[Optional[float]]:
    """
    Get altitude for multiple coordinates using OpenTopoData API with batching.
    Returns list of elevations corresponding to each location.
    """
    cache_file = CACHE_DIR / "elevation_cache.json"
    
    # Load cache
    cache: dict[str, Optional[float]] = {}
    if cache_file.exists():
        try:
            with open(cache_file, "r") as f:
                cache = json.load(f)
        except Exception:
            pass
    
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
            
        except Exception as e:
            print(f"⚠️ Failed to get elevation for batch: {e}")
            all_elevations.extend([None] * len(batch))
    
    # Save cache
    try:
        with open(cache_file, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass
    
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
    Uses REST Countries API or flagcdn.com.
    """
    if not country_code:
        return None

    cache_key = f"flag_{country_code.lower()}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        # Try flagcdn.com (simple, reliable)
        url = f"https://flagcdn.com/w40/{country_code.lower()}.png"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            image_data = base64.b64encode(response.content).decode("utf-8")
            data_uri = f"data:image/png;base64,{image_data}"
            set_cached(cache_key, data_uri)
            return data_uri
    except Exception:
        pass

    return None


def get_country_map_data_uri(
    country_code: str, lat: Optional[float] = None, lon: Optional[float] = None
) -> Optional[str]:
    """
    Get country map/silhouette image as data URI.
    Tries multiple services to get country outline/silhouette images.
    """
    if not country_code:
        return None

    cache_key = f"map_{country_code.lower()}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    # Try country outline SVG from mapsicon (same as referenced project)
    svg_url = f"https://raw.githubusercontent.com/djaiss/mapsicon/master/all/{country_code.lower()}/vector.svg"
    
    try:
        response = requests.get(svg_url, timeout=5)
        if response.status_code == 200:
            svg_data = response.text
            # Modify fill color to white (like referenced project does)
            svg_data = svg_data.replace('fill="#000000"', 'fill="#ffffff"')
            svg_encoded = base64.b64encode(svg_data.encode("utf-8")).decode("utf-8")
            data_uri = f"data:image/svg+xml;base64,{svg_encoded}"
            set_cached(cache_key, data_uri)
            return data_uri
    except Exception:
        pass

    # Fallback: Use a simple map tile service
    if lat is not None and lon is not None:
        try:
            url = "https://staticmap.openstreetmap.de/staticmap.php"
            params = {
                "center": f"{lat},{lon}",
                "zoom": 4,
                "size": "60x60",
                "format": "png",
                "markers": f"{lat},{lon}",
            }
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                image_data = base64.b64encode(response.content).decode("utf-8")
                data_uri = f"data:image/png;base64,{image_data}"
                set_cached(cache_key, data_uri)
                return data_uri
        except Exception:
            pass

    return None


def get_country_map_dot_position(
    country_code: str, lat: float, lon: float
) -> Optional[Tuple[float, float]]:
    """
    Calculate the relative position (0-100%) of a location dot within a country map.
    Uses geodesic calculations for accuracy (like referenced project).
    Returns (x_percent, y_percent) where 0,0 is top-left and 100,100 is bottom-right.
    """
    country_bounds = _load_country_bounds()
    country_code_lower = country_code.lower()
    
    if not country_code or country_code_lower not in country_bounds:
        # Default: center of map
        return (50.0, 50.0)

    bounding_box = country_bounds[country_code_lower]
    
    # Handle both old format (lat_min/max) and new format (sw/ne)
    if "sw" in bounding_box and "ne" in bounding_box:
        # New format with sw/ne
        sw = bounding_box["sw"]
        ne = bounding_box["ne"]
        
        # Calculate distances using geodesic calculations
        _, _, total_lat_distance = _GEOD.inv(sw["lon"], sw["lat"], sw["lon"], ne["lat"])
        _, _, total_lon_distance = _GEOD.inv(sw["lon"], sw["lat"], ne["lon"], sw["lat"])
        
        # Calculate maximum distance for square scaling
        max_distance = max(total_lat_distance, total_lon_distance)
        min_distance = min(total_lat_distance, total_lon_distance)
        diff_distance = max_distance - min_distance
        
        # Calculate distance from southwest to step's location
        _, _, lat_distance = _GEOD.inv(sw["lon"], sw["lat"], sw["lon"], lat)
        _, _, lon_distance = _GEOD.inv(sw["lon"], sw["lat"], lon, sw["lat"])
        
        # Adjust for square scaling
        if max_distance == total_lat_distance:
            lon_distance += diff_distance / 2
        else:
            lat_distance += diff_distance / 2
        
        # Calculate percentages (inverted Y for SVG coordinates)
        lat_percentage = (lat_distance / max_distance) * 100
        lon_percentage = (lon_distance / max_distance) * 100
        
        # Clamp to 5-95% to keep dot visible
        lat_percentage = max(5, min(95, lat_percentage))
        lon_percentage = max(5, min(95, lon_percentage))
        
        return (lon_percentage, lat_percentage)
    else:
        # Old format fallback (lat_min/max, lon_min/max)
        lat_min = bounding_box.get("lat_min")
        lat_max = bounding_box.get("lat_max")
        lon_min = bounding_box.get("lon_min")
        lon_max = bounding_box.get("lon_max")
        
        if lat_min is None or lat_max is None or lon_min is None or lon_max is None:
            return (50.0, 50.0)
        
        lat_range = lat_max - lat_min
        lon_range = lon_max - lon_min
        
        if lat_range == 0 or lon_range == 0:
            return (50.0, 50.0)
        
        # Normalize to 0-100% (inverted Y because SVG coordinates start at top)
        x_percent = ((lon - lon_min) / lon_range) * 100
        y_percent = ((lat_max - lat) / lat_range) * 100
        
        # Clamp to 5-95% to keep dot visible
        x_percent = max(5, min(95, x_percent))
        y_percent = max(5, min(95, y_percent))
        
        return (x_percent, y_percent)


def format_altitude(altitude: Optional[float]) -> str:
    """Format altitude in meters with proper formatting."""
    if altitude is None:
        return "N/A"

    # Round to nearest meter
    meters = int(round(altitude))
    return f"{meters:,}"

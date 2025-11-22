"""Country map generation and dot positioning."""

import json
import re
import base64
import requests
from typing import Optional, Tuple
from pathlib import Path

try:
    import geopandas as gpd
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.geometry import Point

    HAS_GEO = True
except ImportError:
    HAS_GEO = False

from .cache import get_cached, set_cached, CACHE_DIR

_COUNTRY_BOUNDS = None
_SVG_VIEWBOXES = {}
_SVG_PATH_BOUNDS = {}
_SVG_TRANSFORMS = {}


def _load_country_bounds() -> dict:
    """Load country bounds from JSON file (fallback)."""
    global _COUNTRY_BOUNDS
    if _COUNTRY_BOUNDS is None:
        bounds_file = Path(__file__).parent.parent / "country_bounding_boxes.json"
        with open(bounds_file, "r") as f:
            _COUNTRY_BOUNDS = json.load(f)
    return _COUNTRY_BOUNDS


def _generate_geo_calibrated_svg(
    country_code: str, width: int = 1024, height: int = 1024
) -> Optional[str]:
    """Generate a geo-calibrated SVG map of a country using geopandas and Natural Earth Data."""
    if not HAS_GEO:
        return None

    country_code_lower = country_code.lower()

    try:
        ne_50m_url = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
        cache_key_data = "ne_50m_admin_0_countries"

        cache_file = CACHE_DIR / f"{cache_key_data}.geojson"
        if cache_file.exists():
            try:
                world = gpd.read_file(str(cache_file))
            except:
                world = None
        else:
            world = None

        if world is None:
            try:
                print(f"Downloading Natural Earth 50m data for {country_code}...")
                world = gpd.read_file(ne_50m_url)
                world.to_file(str(cache_file), driver="GeoJSON")
            except Exception as e:
                print(f"⚠️ Failed to download Natural Earth 50m data: {e}")
                return None

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

        country_gdf = world[world["ADMIN"] == country_name]

        if country_gdf.empty:
            country_gdf = world[
                world["ADMIN"].str.contains(country_name, case=False, na=False)
            ]

        if country_gdf.empty:
            return None

        gdf = country_gdf.iloc[[0]]

        bounds = gdf.total_bounds
        min_lon, min_lat, max_lon, max_lat = bounds[0], bounds[1], bounds[2], bounds[3]

        local_crs = gdf.estimate_utm_crs()
        gdf_proj = gdf.to_crs(local_crs)
        bounds_proj = gdf_proj.total_bounds

        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        ax.set_xlim(bounds_proj[0], bounds_proj[2])
        ax.set_ylim(bounds_proj[1], bounds_proj[3])
        ax.set_aspect("equal")
        ax.axis("off")

        gdf_proj.plot(ax=ax, color="white", edgecolor="none", linewidth=0)

        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        actual_bounds = [xlim[0], ylim[0], xlim[1], ylim[1]]

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

        viewbox_match = re.search(r'viewBox="([^"]+)"', svg_data)
        if viewbox_match:
            viewbox = viewbox_match.group(1)
            viewbox_vals = [float(x) for x in viewbox_match.group(1).split()]
        else:
            viewbox = "0 0 100 100"
            viewbox_vals = [0, 0, 100, 100]

        geo_bounds_attr = f'data-geo-bounds="{min_lon},{min_lat},{max_lon},{max_lat}"'
        proj_bounds_attr = f'data-proj-bounds="{actual_bounds[0]},{actual_bounds[1]},{actual_bounds[2]},{actual_bounds[3]}"'
        crs_attr = f'data-crs="{local_crs.to_string()}"'
        svg_data = re.sub(
            r"<svg([^>]*)>",
            f"<svg\\1 {geo_bounds_attr} {proj_bounds_attr} {crs_attr}>",
            svg_data,
            count=1,
        )

        svg_data = re.sub(r'fill="[^"]*"', 'fill="#ffffff"', svg_data)
        svg_data = re.sub(
            r"<path([^>]*?)(?:\s|>)(?!.*fill=)", r'<path\1 fill="#ffffff"', svg_data
        )

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

    if HAS_GEO:
        svg_data = _generate_geo_calibrated_svg(country_code)
        if svg_data:
            set_cached(cache_key_svg, svg_data)
            return svg_data

    svg_url = f"https://raw.githubusercontent.com/djaiss/mapsicon/master/all/{country_code.lower()}/vector.svg"

    try:
        response = requests.get(svg_url, timeout=10)
        response.raise_for_status()
        if response.status_code == 200:
            svg_data = response.text

            viewbox_match = re.search(r'viewBox="([^"]+)"', svg_data)
            if viewbox_match:
                viewbox_str = viewbox_match.group(1)
                viewbox = [float(x) for x in viewbox_str.split()]
                if len(viewbox) == 4:
                    _SVG_VIEWBOXES[country_code.lower()] = viewbox

            transform_match = re.search(r'transform="([^"]+)"', svg_data)
            if transform_match:
                transform_str = transform_match.group(1)
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

            paths = re.findall(r'<path[^>]*d="([^"]+)"', svg_data)
            if paths:
                all_x = []
                all_y = []
                for path_d in paths:
                    numbers = re.findall(r"-?\d+\.?\d*", path_d)
                    for i, num_str in enumerate(numbers):
                        try:
                            num = float(num_str)
                            if i % 2 == 0:
                                all_x.append(num)
                            else:
                                all_y.append(num)
                        except ValueError:
                            continue

                if all_x and all_y:
                    path_bounds = {
                        "min_x": min(all_x),
                        "max_x": max(all_x),
                        "min_y": min(all_y),
                        "max_y": max(all_y),
                    }
                    _SVG_PATH_BOUNDS[country_code.lower()] = path_bounds

                    transform = _SVG_TRANSFORMS.get(country_code.lower())
                    if transform and viewbox:
                        scale_x = transform["scale_x"]
                        scale_y = transform["scale_y"]
                        translate_x = transform["translate_x"]
                        translate_y = transform["translate_y"]

                        rendered_min_x = path_bounds["min_x"] * scale_x + translate_x
                        rendered_max_x = path_bounds["max_x"] * scale_x + translate_x
                        rendered_min_y = path_bounds["min_y"] * scale_y + translate_y
                        rendered_max_y = path_bounds["max_y"] * scale_y + translate_y

                        _SVG_PATH_BOUNDS[country_code.lower()]["rendered"] = {
                            "min_x": rendered_min_x,
                            "max_x": rendered_max_x,
                            "min_y": rendered_min_y,
                            "max_y": rendered_max_y,
                        }

            svg_data = re.sub(r'fill="#000000"', 'fill="#ffffff"', svg_data)
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
    """Get country map/silhouette image as data URI."""
    if not country_code:
        return None

    cache_key = f"map_{country_code.lower()}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    svg_data = get_country_map_svg(country_code, lat, lon)
    if svg_data:
        svg_encoded = base64.b64encode(svg_data.encode("utf-8")).decode("utf-8")
        data_uri = f"data:image/svg+xml;base64,{svg_encoded}"
        set_cached(cache_key, data_uri)
        return data_uri

    return None


def get_country_map_dot_position(
    country_code: str, lat: float, lon: float
) -> Optional[Tuple[float, float]]:
    """Calculate the relative position (0-100%) of a location dot within a country map."""
    country_code_lower = country_code.lower()

    if not country_code:
        return (50.0, 50.0)

    svg_data = get_country_map_svg(country_code_lower)

    if svg_data:
        geo_bounds_match = re.search(r'data-geo-bounds="([^"]+)"', svg_data)
        if geo_bounds_match:
            bounds_str = geo_bounds_match.group(1)
            bounds = [float(x) for x in bounds_str.split(",")]
            if len(bounds) == 4:
                min_lon, min_lat, max_lon, max_lat = bounds

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

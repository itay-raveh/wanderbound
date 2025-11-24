"""Country map generation and dot positioning."""

import base64
import json
import re
from pathlib import Path
from typing import Any

from lxml import etree

try:
    import geopandas as gpd
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.geometry import Point

    HAS_GEO = True
except ImportError:
    HAS_GEO = False

from ..logger import get_logger
from ..settings import get_settings
from .cache import CACHE_DIR, get_cached, set_cached
from .rate_limit import fetch_text_with_retry

logger = get_logger(__name__)

# Maps API rate limit: Conservative rate for GitHub raw URLs
MAPS_API_CALLS_PER_SECOND = 2

_COUNTRY_BOUNDS: dict[str, Any] | None = None
_SVG_VIEWBOXES: dict[str, list[float]] = {}
_SVG_PATH_BOUNDS: dict[str, dict[str, float | dict[str, float]]] = {}
_SVG_TRANSFORMS: dict[str, dict[str, float]] = {}


def _parse_svg_with_lxml(svg_data: str) -> etree._Element | None:
    """Parse SVG string using lxml."""
    try:
        # Remove XML declaration and DOCTYPE if present (to avoid DTD fetching)
        svg_clean = svg_data
        lines = svg_clean.split("\n")
        cleaned_lines = []
        skip_doctype = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("<?xml"):
                continue  # Skip XML declaration
            elif stripped.startswith("<!DOCTYPE"):
                skip_doctype = True
                continue  # Skip DOCTYPE line
            elif skip_doctype and ">" in line and not stripped.startswith("<"):
                # Skip continuation of DOCTYPE if it spans multiple lines
                if ">" in line:
                    skip_doctype = False
                continue
            elif skip_doctype:
                # Still in DOCTYPE block
                if ">" in line:
                    skip_doctype = False
                continue
            else:
                cleaned_lines.append(line)

        svg_clean = "\n".join(cleaned_lines)

        # Use parser that doesn't fetch external DTDs
        parser = etree.XMLParser(
            recover=True,
            strip_cdata=False,
            no_network=True,  # Don't fetch external DTDs
            huge_tree=True,  # Allow large SVG files
        )
        root = etree.fromstring(svg_clean.encode("utf-8"), parser=parser)

        # Register SVG namespace if not already registered
        if (
            root is not None
            and hasattr(root, "nsmap")
            and root.nsmap
            and "http://www.w3.org/2000/svg" not in root.nsmap.values()
        ):
            etree.register_namespace("svg", "http://www.w3.org/2000/svg")

        return root
    except (etree.XMLSyntaxError, etree.ParseError, ValueError) as e:
        logger.error(f"Error parsing SVG with lxml: {e}", exc_info=True)
        return None


def _get_svg_viewbox(root: etree._Element) -> list[float] | None:
    """Extract viewBox from SVG root element."""
    viewbox_str = root.get("viewBox")
    if viewbox_str:
        try:
            viewbox = [float(x) for x in viewbox_str.split()]
            if len(viewbox) == 4:
                return viewbox
        except (ValueError, AttributeError):
            pass
    return None


def _parse_transform(transform_str: str) -> dict[str, float]:
    """Parse SVG transform string into translate and scale values."""
    translate_x: float = 0.0
    translate_y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0

    if not transform_str:
        return {
            "translate_x": translate_x,
            "translate_y": translate_y,
            "scale_x": scale_x,
            "scale_y": scale_y,
        }

    # Parse translate
    # Extract translate and scale from SVG transform string
    translate_match = re.search(r"translate\(([^)]+)\)", transform_str)
    if translate_match:
        translate_parts = [
            float(x.strip()) for x in translate_match.group(1).split(",")
        ]
        if len(translate_parts) >= 2:
            translate_x, translate_y = translate_parts[0], translate_parts[1]

    scale_match = re.search(r"scale\(([^)]+)\)", transform_str)
    if scale_match:
        scale_parts = [float(x.strip()) for x in scale_match.group(1).split(",")]
        if len(scale_parts) >= 2:
            scale_x, scale_y = scale_parts[0], scale_parts[1]
        elif len(scale_parts) == 1:
            scale_x = scale_y = scale_parts[0]

    return {
        "translate_x": translate_x,
        "translate_y": translate_y,
        "scale_x": scale_x,
        "scale_y": scale_y,
    }


def _extract_path_bounds(root: etree._Element) -> dict[str, float] | None:
    """Extract bounding box from all path elements in SVG."""
    all_x = []
    all_y = []

    # Find all path elements (handle both namespaced and non-namespaced)
    paths_raw = root.xpath('.//*[local-name()="path"][@d]')
    if not isinstance(paths_raw, list):
        return None
    for path_raw in paths_raw:
        if not isinstance(path_raw, etree._Element):
            continue
        path = path_raw
        path_d = path.get("d", "")
        # Extract numbers from path data
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
        return {
            "min_x": min(all_x),
            "max_x": max(all_x),
            "min_y": min(all_y),
            "max_y": max(all_y),
        }
    return None


def _svg_to_string(root: etree._Element) -> str:
    """Convert SVG element tree to string."""
    return etree.tostring(root, encoding="unicode", pretty_print=False)


def _load_country_bounds() -> dict[str, Any]:
    """Load country bounds from JSON file (fallback)."""
    global _COUNTRY_BOUNDS
    if _COUNTRY_BOUNDS is None:
        bounds_file = Path(__file__).parent.parent / "country_bounding_boxes.json"
        with open(bounds_file) as f:
            _COUNTRY_BOUNDS = json.load(f)
    assert _COUNTRY_BOUNDS is not None
    return _COUNTRY_BOUNDS


def _load_natural_earth_data(country_code: str) -> Any | None:
    """Load Natural Earth GeoJSON data from cache or download it.

    Args:
        country_code: ISO country code (for logging purposes)

    Returns:
        GeoDataFrame with Natural Earth data, or None if loading fails
    """
    settings = get_settings()
    ne_50m_url = settings.natural_earth_geojson_url
    cache_key_data = "ne_50m_admin_0_countries"

    cache_file = CACHE_DIR / f"{cache_key_data}.geojson"
    if cache_file.exists():
        try:
            return gpd.read_file(str(cache_file))
        except (OSError, ValueError) as e:
            logger.debug(f"Failed to read cached Natural Earth data: {e}")

    try:
        logger.info(f"Downloading Natural Earth 50m data for {country_code}...")
        world = gpd.read_file(ne_50m_url)
        world.to_file(str(cache_file), driver="GeoJSON")
        logger.debug(f"Cached Natural Earth data to {cache_file}")
        return world
    except OSError as e:
        logger.error(f"Failed to download Natural Earth 50m data: {e}", exc_info=True)
        return None


def _find_country_in_geodataframe(world: Any, country_code_lower: str) -> Any | None:
    """Find country GeoDataFrame by ISO code or name.

    Args:
        world: GeoDataFrame with Natural Earth data
        country_code_lower: Lowercase ISO country code

    Returns:
        GeoDataFrame for the country, or None if not found
    """
    # Try to find country by ISO_A2 code first (most reliable)
    if "ISO_A2" in world.columns:
        country_gdf = world[world["ISO_A2"] == country_code_lower.upper()]
        if not country_gdf.empty:
            return country_gdf

    # Fallback to ADMIN name matching
    fallback_names: dict[str, str] = {
        "gf": "France",  # French Guiana is part of France in Natural Earth
        "fk": "Falkland Islands",
    }
    country_name = fallback_names.get(country_code_lower)
    if country_name and "ADMIN" in world.columns:
        country_gdf = world[world["ADMIN"] == country_name]
        if country_gdf.empty:
            country_gdf = world[
                world["ADMIN"].str.contains(country_name, case=False, na=False)
            ]
        if not country_gdf.empty:
            return country_gdf

    # Try direct ADMIN match with country code as fallback
    if "ADMIN" in world.columns:
        country_gdf = world[
            world["ADMIN"].str.contains(country_code_lower, case=False, na=False)
        ]
        if not country_gdf.empty:
            return country_gdf

    return None


def _generate_svg_plot(
    gdf: Any, width: int, height: int
) -> tuple[str, list[float], Any]:
    """Generate SVG plot from GeoDataFrame.

    Args:
        gdf: GeoDataFrame for the country
        width: Output SVG width in pixels
        height: Output SVG height in pixels

    Returns:
        Tuple of (svg_data, actual_bounds, local_crs)
    """
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

    return svg_data, actual_bounds, local_crs


def _process_svg_with_geo_attributes(
    root: etree._Element,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    actual_bounds: list[float],
    local_crs: Any,
) -> str:
    """Add geo-calibration attributes to SVG and set all fills to white.

    Args:
        root: SVG root element
        min_lon: Minimum longitude
        min_lat: Minimum latitude
        max_lon: Maximum longitude
        max_lat: Maximum latitude
        actual_bounds: Projected bounds [min_x, min_y, max_x, max_y]
        local_crs: Coordinate reference system

    Returns:
        SVG string with geo attributes
    """
    # Get or set viewBox
    viewbox_vals = _get_svg_viewbox(root)
    if viewbox_vals is None:
        root.set("viewBox", "0 0 100 100")

    # Add custom geo-calibration attributes
    root.set("data-geo-bounds", f"{min_lon},{min_lat},{max_lon},{max_lat}")
    root.set(
        "data-proj-bounds",
        f"{actual_bounds[0]},{actual_bounds[1]},{actual_bounds[2]},{actual_bounds[3]}",
    )
    root.set("data-crs", local_crs.to_string())

    # Set all fills to white
    for elem in root.iter():
        if (
            elem.tag.endswith("path")
            or elem.tag.endswith("polygon")
            or elem.tag.endswith("circle")
            or elem.tag.endswith("rect")
        ) or "fill" in elem.attrib:
            elem.set("fill", "#ffffff")

    return _svg_to_string(root)


def _generate_geo_calibrated_svg(
    country_code: str, width: int = 1024, height: int = 1024
) -> str | None:
    """Generate a geo-calibrated SVG map of a country using geopandas and Natural Earth Data.

    Args:
        country_code: ISO country code (e.g., "us", "fr")
        width: Output SVG width in pixels (default: 1024)
        height: Output SVG height in pixels (default: 1024)

    Returns:
        SVG string with geo-calibrated viewBox, or None if generation fails
    """
    if not HAS_GEO:
        return None

    country_code_lower = country_code.lower()

    try:
        world = _load_natural_earth_data(country_code)
        if world is None:
            return None

        country_gdf = _find_country_in_geodataframe(world, country_code_lower)
        if country_gdf is None or country_gdf.empty:
            return None

        gdf = country_gdf.iloc[[0]]
        bounds = gdf.total_bounds
        min_lon, min_lat, max_lon, max_lat = bounds[0], bounds[1], bounds[2], bounds[3]

        svg_data, actual_bounds, local_crs = _generate_svg_plot(gdf, width, height)

        root = _parse_svg_with_lxml(svg_data)
        if root is None:
            return None

        return _process_svg_with_geo_attributes(
            root, min_lon, min_lat, max_lon, max_lat, actual_bounds, local_crs
        )

    except Exception as e:
        logger.error(
            f"Error generating geo-calibrated SVG for {country_code}: {e}",
            exc_info=True,
        )
        return None


def get_country_map_svg(
    country_code: str, lat: float | None = None, lon: float | None = None
) -> str | None:
    """Get country map/silhouette as raw SVG string."""
    if not country_code:
        return None

    cache_key_svg = f"map_svg_{country_code.lower()}"
    cached_svg = get_cached(cache_key_svg)
    if cached_svg is not None and isinstance(cached_svg, str):
        return str(cached_svg)

    if HAS_GEO:
        svg_data = _generate_geo_calibrated_svg(country_code)
        if svg_data:
            set_cached(cache_key_svg, svg_data)
            return svg_data

    settings = get_settings()
    svg_url = settings.mapsicon_url.format(country_code=country_code.lower())

    try:
        svg_data = fetch_text_with_retry(
            svg_url,
            calls_per_second=MAPS_API_CALLS_PER_SECOND,
        )

        # Parse SVG with lxml
        root = _parse_svg_with_lxml(svg_data)
        if root is None:
            return None

        # Extract viewBox
        viewbox = _get_svg_viewbox(root)
        if viewbox and len(viewbox) == 4:
            _SVG_VIEWBOXES[country_code.lower()] = viewbox

        # Extract transform from root or first group element (handle namespaces)
        transform_elem = root
        group_raw = root.xpath('.//*[local-name()="g"][@transform]')
        if isinstance(group_raw, list) and len(group_raw) > 0:
            first_elem = group_raw[0]
            if isinstance(first_elem, etree._Element):
                transform_elem = first_elem
            else:
                transform_elem = root
        else:
            transform_elem = root

        transform_str = transform_elem.get("transform", "")
        if transform_str:
            transform_data = _parse_transform(transform_str)
            _SVG_TRANSFORMS[country_code.lower()] = transform_data

        path_bounds = _extract_path_bounds(root)
        if path_bounds:
            _SVG_PATH_BOUNDS[country_code.lower()] = path_bounds  # type: ignore[assignment]

            transform = _SVG_TRANSFORMS.get(country_code.lower())
            if transform and viewbox and len(viewbox) == 4:
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

        # Set fills to white
        for elem in root.iter():
            if (
                elem.tag.endswith("path")
                or elem.tag.endswith("polygon")
                or elem.tag.endswith("circle")
                or elem.tag.endswith("rect")
            ):
                fill = elem.get("fill", "")
                if fill == "#000000" or fill == "black":
                    elem.set("fill", "#ffffff")
            elif "fill" in elem.attrib:
                if elem.get("fill") == "#000000" or elem.get("fill") == "black":
                    elem.set("fill", "#ffffff")

        svg_data = _svg_to_string(root)
        set_cached(cache_key_svg, svg_data)
        return svg_data
    except Exception as e:
        logger.warning(f"Failed to get map for {country_code}: {e}")

    return None


def get_country_map_data_uri(
    country_code: str, lat: float | None = None, lon: float | None = None
) -> str | None:
    """Get country map/silhouette image as data URI."""
    if not country_code:
        return None

    cache_key = f"map_{country_code.lower()}"
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, str):
        return str(cached)

    svg_data = get_country_map_svg(country_code, lat, lon)
    if svg_data:
        svg_encoded = base64.b64encode(svg_data.encode("utf-8")).decode("utf-8")
        data_uri = f"data:image/svg+xml;base64,{svg_encoded}"
        set_cached(cache_key, data_uri)
        return data_uri

    return None


def get_country_map_dot_position(
    country_code: str, lat: float, lon: float
) -> tuple[float, float] | None:
    """Calculate the relative position (0-100%) of a location dot within a country map.

    Args:
        country_code: ISO country code (e.g., "us", "fr")
        lat: Latitude of the location point
        lon: Longitude of the location point

    Returns:
        Tuple of (x_percent, y_percent) where values are 0-100, or None if calculation fails
    """
    country_code_lower = country_code.lower()

    if not country_code:
        return (50.0, 50.0)

    svg_data = get_country_map_svg(country_code_lower)

    if svg_data:
        root = _parse_svg_with_lxml(svg_data)
        if root is not None:
            # Extract data attributes
            geo_bounds_str = root.get("data-geo-bounds")
            if geo_bounds_str:
                try:
                    bounds = [float(x) for x in geo_bounds_str.split(",")]
                    if len(bounds) == 4:
                        min_lon, min_lat, max_lon, max_lat = bounds

                        viewbox = _get_svg_viewbox(root)
                        proj_bounds_str = root.get("data-proj-bounds")
                        crs_str = root.get("data-crs")

                        if viewbox and proj_bounds_str and crs_str:
                            try:
                                proj_bounds = [
                                    float(x) for x in proj_bounds_str.split(",")
                                ]
                                if len(viewbox) == 4 and len(proj_bounds) == 4:
                                    point_geo = gpd.GeoDataFrame(
                                        geometry=[Point(lon, lat)], crs="EPSG:4326"
                                    )
                                    point_proj = point_geo.to_crs(crs_str)

                                    proj_x = point_proj.geometry.iloc[0].x  # type: ignore[attr-defined]
                                    proj_y = point_proj.geometry.iloc[0].y  # type: ignore[attr-defined]

                                    proj_min_x, proj_min_y, proj_max_x, proj_max_y = (
                                        proj_bounds
                                    )
                                    proj_width = proj_max_x - proj_min_x
                                    proj_height = proj_max_y - proj_min_y

                                    x_ratio = (proj_x - proj_min_x) / proj_width
                                    y_ratio = (proj_max_y - proj_y) / proj_height

                                    x_percent = x_ratio * 100
                                    y_percent = y_ratio * 100

                                    x_percent = max(0, min(100, x_percent))
                                    y_percent = max(0, min(100, y_percent))

                                    return (x_percent, y_percent)
                            except (ValueError, AttributeError):
                                pass

                        if viewbox and len(viewbox) == 4:
                            viewbox_min_lon = viewbox[0]
                            viewbox[1]
                            viewbox_width = viewbox[2]
                            viewbox_height = viewbox[3]

                            x_percent = ((lon - viewbox_min_lon) / viewbox_width) * 100
                            y_percent = ((max_lat - lat) / abs(viewbox_height)) * 100

                            x_percent = max(0, min(100, x_percent))
                            y_percent = max(0, min(100, y_percent))

                            return (x_percent, y_percent)
                except (ValueError, AttributeError):
                    pass

    rendered_bounds_raw = _SVG_PATH_BOUNDS.get(country_code_lower, {}).get("rendered")
    viewbox = _SVG_VIEWBOXES.get(country_code_lower)

    if (
        rendered_bounds_raw
        and isinstance(rendered_bounds_raw, dict)
        and viewbox
        and len(viewbox) == 4
    ):
        rendered_bounds: dict[str, float] = rendered_bounds_raw
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

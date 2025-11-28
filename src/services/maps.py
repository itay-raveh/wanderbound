"""Country map generation and dot positioning."""

import base64
import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import httpx
from lxml import etree
from shapely.geometry import MultiPolygon, Point, Polygon

from src.core.logger import get_logger
from src.core.settings import settings

from .utils import CACHE_DIR, get_cached, set_cached

logger = get_logger(__name__)


def _remove_xml_declarations(svg_data: str) -> str:
    """Remove XML declaration and DOCTYPE from SVG to avoid DTD fetching."""
    lines = svg_data.split("\n")
    cleaned_lines = []
    skip_doctype = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("<?xml"):
            continue
        if stripped.startswith("<!DOCTYPE"):
            skip_doctype = True
            continue
        if skip_doctype:
            if ">" in line:
                skip_doctype = False
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def _parse_svg_with_lxml(svg_data: str) -> etree._Element | None:
    try:
        svg_clean = _remove_xml_declarations(svg_data)

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
    except (etree.XMLSyntaxError, etree.ParseError, ValueError):
        logger.exception("Error parsing SVG with lxml")
        return None
    else:
        return root


def _get_svg_viewbox(root: etree._Element) -> list[float] | None:
    viewbox_str = root.get("viewBox")
    if viewbox_str:
        try:
            viewbox = [float(x) for x in viewbox_str.split()]
            if len(viewbox) == 4:
                return viewbox
        except (ValueError, AttributeError):
            pass
    return None


# Module-level country bounds cache (lazy-loaded)
# Python modules are singletons, so this ensures only one instance
_COUNTRY_BOUNDS: dict[str, Any] | None = None


def _load_country_bounds() -> dict[str, Any]:
    """Load country bounds from JSON file (fallback)."""
    global _COUNTRY_BOUNDS  # noqa: PLW0603
    if _COUNTRY_BOUNDS is None:
        bounds_file = Path(__file__).parent.parent / "country_bounding_boxes.json"
        with bounds_file.open() as f:
            _COUNTRY_BOUNDS = json.load(f)
        if _COUNTRY_BOUNDS is None:
            raise RuntimeError("Failed to load country bounds")
    return _COUNTRY_BOUNDS


def _load_natural_earth_data(country_code: str) -> Any | None:
    """Load Natural Earth GeoJSON data from cache or download it."""
    ne_50m_url = settings.natural_earth_geojson_url
    cache_key_data = "ne_50m_admin_0_countries"

    cache_file = CACHE_DIR / f"{cache_key_data}.geojson"
    if cache_file.exists():
        try:
            return gpd.read_file(str(cache_file))
        except (OSError, ValueError) as e:
            logger.debug("Failed to read cached Natural Earth data: %s", e)

    try:
        logger.info("Downloading Natural Earth 50m data for %s...", country_code)
        world = gpd.read_file(ne_50m_url)
        world.to_file(str(cache_file), driver="GeoJSON")
        logger.debug("Cached Natural Earth data to %s", cache_file)
    except OSError:
        logger.exception("Failed to download Natural Earth 50m data")
        return None
    else:
        return world


def _find_country_in_geodataframe(world: Any, country_code_lower: str) -> Any | None:
    """Find country GeoDataFrame by ISO code or name."""
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
            country_gdf = world[world["ADMIN"].str.contains(country_name, case=False, na=False)]
        if not country_gdf.empty:
            return country_gdf

    # Try direct ADMIN match with country code as fallback
    if "ADMIN" in world.columns:
        country_gdf = world[world["ADMIN"].str.contains(country_code_lower, case=False, na=False)]
        if not country_gdf.empty:
            return country_gdf

    return None


def _coords_to_svg_path(
    coords: list[tuple[float, float]],
    *,
    closed: bool = False,
    flip_y: tuple[float, float] | None = None,
) -> str:
    """Convert coordinate list to SVG path commands."""
    if len(coords) < 2:
        return ""

    # Flip Y coordinates if needed (SVG Y increases downward, geographic Y increases upward)
    if flip_y is not None:
        min_y, max_y = flip_y
        center_y = (min_y + max_y) / 2
        flipped_coords = [(x, 2 * center_y - y) for x, y in coords]
    else:
        flipped_coords = coords

    path_parts = [f"M {flipped_coords[0][0]},{flipped_coords[0][1]}"] + [
        f"L {coord[0]},{coord[1]}" for coord in flipped_coords[1:]
    ]
    if closed:
        path_parts.append("Z")
    return " ".join(path_parts)


def _polygon_to_svg_path(polygon: Polygon, flip_y: tuple[float, float] | None = None) -> str:
    """Convert Polygon geometry to SVG path."""
    path_parts = []
    # Exterior ring
    exterior_coords = list(polygon.exterior.coords)
    if len(exterior_coords) >= 2:
        path_parts.append(_coords_to_svg_path(exterior_coords, closed=True, flip_y=flip_y))

    # Interior rings (holes)
    for interior in polygon.interiors:
        interior_coords = list(interior.coords)
        if len(interior_coords) >= 2:
            path_parts.append(_coords_to_svg_path(interior_coords, closed=True, flip_y=flip_y))

    return " ".join(path_parts) if path_parts else ""


def _multipolygon_to_svg_path(
    multipolygon: MultiPolygon, flip_y: tuple[float, float] | None = None
) -> str:
    """Convert MultiPolygon geometry to SVG path."""
    paths = []
    for poly in multipolygon.geoms:
        path = _polygon_to_svg_path(poly, flip_y=flip_y)
        if path:
            paths.append(path)
    return " ".join(paths)


def _geometry_to_svg_path(geometry: Any, flip_y: tuple[float, float] | None = None) -> str:
    """Convert Shapely geometry to SVG path data string."""
    if geometry.is_empty:
        return ""

    if isinstance(geometry, Polygon):
        return _polygon_to_svg_path(geometry, flip_y=flip_y)

    if isinstance(geometry, MultiPolygon):
        return _multipolygon_to_svg_path(geometry, flip_y=flip_y)

    # Fallback: try to get coordinates
    try:
        coords = list(geometry.coords)
        closed = getattr(geometry, "is_closed", False)
        return _coords_to_svg_path(coords, closed=closed, flip_y=flip_y)
    except (AttributeError, TypeError):
        return ""


def _generate_svg_plot(gdf: Any, width: int, height: int) -> tuple[str, list[float], Any]:
    """Generate SVG plot from GeoDataFrame without matplotlib."""
    local_crs = gdf.estimate_utm_crs()
    gdf_proj = gdf.to_crs(local_crs)
    bounds_proj = gdf_proj.total_bounds

    # Calculate actual bounds (same as what matplotlib would produce)
    min_x, min_y, max_x, max_y = bounds_proj
    actual_bounds = [min_x, min_y, max_x, max_y]

    # Calculate viewBox dimensions
    viewbox_width = max_x - min_x
    viewbox_height = max_y - min_y

    # Create SVG root element
    svg_ns = "http://www.w3.org/2000/svg"
    root = etree.Element(f"{{{svg_ns}}}svg", nsmap={None: svg_ns})
    root.set("width", str(width))
    root.set("height", str(height))
    # Keep original viewBox - coordinates will be flipped during path generation
    root.set("viewBox", f"{min_x} {min_y} {viewbox_width} {viewbox_height}")
    root.set("xmlns", svg_ns)

    # Create group for paths
    # SVG Y-axis increases downward, geographic coordinates increase upward (north)
    # We'll flip Y coordinates directly in path generation around the center
    group = etree.SubElement(root, f"{{{svg_ns}}}g")
    group.set("fill", "#ffffff")
    group.set("stroke", "none")

    # Flip Y coordinates around center to correct orientation
    # This keeps flipped coordinates within the original viewBox bounds
    flip_y_bounds = (min_y, max_y)

    # Convert each geometry to SVG path with flipped Y coordinates
    for _idx, row in gdf_proj.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty:
            continue

        path_data = _geometry_to_svg_path(geometry, flip_y=flip_y_bounds)
        if path_data:
            path_elem = etree.SubElement(group, f"{{{svg_ns}}}path")
            path_elem.set("d", path_data)

    # Convert to string
    svg_data_str = etree.tostring(root, encoding="unicode", pretty_print=False)
    svg_data: str = str(svg_data_str)  # Ensure it's a string for type checking

    return svg_data, actual_bounds, local_crs


def _process_svg_with_geo_attributes(
    root: etree._Element,
    geo_bounds: tuple[float, float, float, float],
    actual_bounds: list[float],
    local_crs: Any,
) -> str:
    """Add geo-calibration attributes to SVG and set all fills to white."""
    min_lon, min_lat, max_lon, max_lat = geo_bounds

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

    svg_str = etree.tostring(root, encoding="unicode", pretty_print=False)
    return str(svg_str)


def _generate_geo_calibrated_svg(
    country_code: str, width: int = 1024, height: int = 1024
) -> str | None:
    """Generate a geo-calibrated SVG map of a country using geopandas and Natural Earth Data.

    The SVG dimensions are adjusted to match the country's aspect ratio to prevent
    dots from spreading across empty space for narrow countries.
    """
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

        # Project to local CRS to get accurate aspect ratio for the SVG viewBox
        # Geographic aspect ratio (lat/lon degrees) doesn't match projected aspect ratio
        local_crs = gdf.estimate_utm_crs()
        gdf_proj = gdf.to_crs(local_crs)
        bounds_proj = gdf_proj.total_bounds
        proj_min_x, proj_min_y, proj_max_x, proj_max_y = bounds_proj

        # Calculate aspect ratio from projected coordinates (matches the viewBox)
        proj_width = proj_max_x - proj_min_x
        proj_height = proj_max_y - proj_min_y
        country_aspect_ratio = proj_width / proj_height if proj_height > 0 else 1.0

        # Adjust SVG dimensions to match projected aspect ratio while respecting max dimensions
        # This ensures the SVG dimensions match the viewBox aspect ratio
        if country_aspect_ratio > 1.0:
            # Country is wider than tall in projected space
            svg_width = min(width, int(height * country_aspect_ratio))
            svg_height = int(svg_width / country_aspect_ratio)
        else:
            # Country is taller than wide in projected space
            svg_height = min(height, int(width / country_aspect_ratio))
            svg_width = int(svg_height * country_aspect_ratio)

        svg_data, actual_bounds, local_crs = _generate_svg_plot(gdf, svg_width, svg_height)

        root = _parse_svg_with_lxml(svg_data)
        if root is None:
            return None

        return _process_svg_with_geo_attributes(
            root, (min_lon, min_lat, max_lon, max_lat), actual_bounds, local_crs
        )

    except Exception:
        logger.exception("Error generating geo-calibrated SVG for %s", country_code)
        return None


def get_country_map_svg(
    country_code: str, _lat: float | None = None, _lon: float | None = None
) -> str | None:
    """Get country map/silhouette as raw SVG string."""
    if not country_code:
        return None

    cache_key_svg = f"map_svg_{country_code.lower()}"
    cached_svg = get_cached(cache_key_svg)
    if cached_svg is not None and isinstance(cached_svg, str):
        return str(cached_svg)

    # Generate geo-calibrated SVG
    svg_data = _generate_geo_calibrated_svg(country_code)
    if svg_data:
        set_cached(cache_key_svg, svg_data)
        return svg_data

    logger.warning("Failed to generate geo-calibrated SVG for %s", country_code)
    return None


def _calculate_position_from_projected_bounds(
    lat: float, lon: float, proj_bounds: list[float], crs_str: str
) -> tuple[float, float] | None:
    """Calculate position using projected bounds and CRS."""
    try:
        point_geo = gpd.GeoDataFrame(geometry=[Point(lon, lat)], crs="EPSG:4326")
        point_proj = point_geo.to_crs(crs_str)

        proj_x = point_proj.geometry.iloc[0].x
        proj_y = point_proj.geometry.iloc[0].y

        proj_min_x, proj_min_y, proj_max_x, proj_max_y = proj_bounds
        proj_width = proj_max_x - proj_min_x
        proj_height = proj_max_y - proj_min_y

        if proj_width == 0 or proj_height == 0:
            return None

        x_ratio = (proj_x - proj_min_x) / proj_width
        y_ratio = (proj_max_y - proj_y) / proj_height

        x_percent = max(0, min(100, x_ratio * 100))
        y_percent = max(0, min(100, y_ratio * 100))
    except (ValueError, AttributeError):
        return None
    else:
        return (x_percent, y_percent)


def _calculate_position_from_viewbox(
    lat: float, lon: float, max_lat: float, viewbox: list[float]
) -> tuple[float, float] | None:
    """Calculate position using viewbox coordinates."""
    if len(viewbox) != 4:
        return None

    viewbox_min_lon = viewbox[0]
    viewbox_width = viewbox[2]
    viewbox_height = viewbox[3]

    if viewbox_width == 0 or viewbox_height == 0:
        return None

    x_percent = ((lon - viewbox_min_lon) / viewbox_width) * 100
    y_percent = ((max_lat - lat) / abs(viewbox_height)) * 100

    x_percent = max(0, min(100, x_percent))
    y_percent = max(0, min(100, y_percent))

    return (x_percent, y_percent)


def _calculate_position_from_svg_root(
    root: Any, lat: float, lon: float
) -> tuple[float, float] | None:
    """Calculate position from SVG root element."""
    geo_bounds_str = root.get("data-geo-bounds")
    if not geo_bounds_str:
        return None

    try:
        bounds = [float(x) for x in geo_bounds_str.split(",")]
        if len(bounds) != 4:
            return None

        _min_lon, _min_lat, _max_lon, max_lat = bounds
        viewbox = _get_svg_viewbox(root)
        proj_bounds_str = root.get("data-proj-bounds")
        crs_str = root.get("data-crs")

        # Try projected bounds first (more accurate)
        if viewbox and proj_bounds_str and crs_str:
            try:
                proj_bounds = [float(x) for x in proj_bounds_str.split(",")]
                if len(viewbox) == 4 and len(proj_bounds) == 4:
                    position = _calculate_position_from_projected_bounds(
                        lat, lon, proj_bounds, crs_str
                    )
                    if position is not None:
                        return position
            except (ValueError, AttributeError):
                pass

        # Fallback to viewbox calculation
        if viewbox and len(viewbox) == 4:
            return _calculate_position_from_viewbox(lat, lon, max_lat, viewbox)

    except (ValueError, AttributeError):
        pass

    return None


def _calculate_position_from_bounds(
    lat: float, lon: float, bounding_box: dict[str, Any]
) -> tuple[float, float] | None:
    """Calculate position from country bounding box."""
    if "sw" not in bounding_box or "ne" not in bounding_box:
        return None

    sw = bounding_box["sw"]
    ne = bounding_box["ne"]

    lat_range = ne["lat"] - sw["lat"]
    lon_range = ne["lon"] - sw["lon"]

    if lat_range == 0 or lon_range == 0:
        return None

    lon_percentage = ((lon - sw["lon"]) / lon_range) * 100
    lat_percentage = ((ne["lat"] - lat) / lat_range) * 100

    lon_percentage = max(5, min(95, lon_percentage))
    lat_percentage = max(5, min(95, lat_percentage))

    return (lon_percentage, lat_percentage)


def get_country_map_dot_position(
    country_code: str, lat: float, lon: float, svg_data: str | None = None
) -> tuple[float, float] | None:
    """Calculate the relative position (0-100%) of a location dot within a country map."""
    if not country_code:
        return (50.0, 50.0)

    if svg_data is None:
        svg_data = get_country_map_svg(country_code.lower())

    if svg_data:
        root = _parse_svg_with_lxml(svg_data)
        if root is not None:
            position = _calculate_position_from_svg_root(root, lat, lon)
            if position is not None:
                return position

    # Fallback to country bounds if geo-calibrated data is not available
    country_code_lower = country_code.lower()
    country_bounds = _load_country_bounds()
    if country_code_lower not in country_bounds:
        return (50.0, 50.0)

    bounding_box = country_bounds[country_code_lower]
    position = _calculate_position_from_bounds(lat, lon, bounding_box)
    return position if position is not None else (50.0, 50.0)


async def get_country_map_svg_async(
    _client: httpx.AsyncClient,
    country_code: str,
    _lat: float | None = None,
    _lon: float | None = None,
) -> str | None:
    """Get country map/silhouette as raw SVG string (async)."""
    if not country_code:
        return None

    cache_key_svg = f"map_svg_{country_code.lower()}"
    cached_svg = get_cached(cache_key_svg)
    if cached_svg is not None and isinstance(cached_svg, str):
        return str(cached_svg)

    # Generate geo-calibrated SVG
    try:
        svg_data = _generate_geo_calibrated_svg(country_code)
        if svg_data:
            set_cached(cache_key_svg, svg_data)
            return svg_data
    except (OSError, ValueError, KeyError, AttributeError, TypeError) as e:
        logger.warning("Failed to generate geo-calibrated SVG for %s: %s", country_code, e)

    return None


async def get_country_map_data_uri_async(
    client: httpx.AsyncClient,
    country_code: str,
    lat: float | None = None,
    lon: float | None = None,
) -> str | None:
    """Get country map/silhouette image as data URI (async)."""
    svg_data = await get_country_map_svg_async(client, country_code, lat, lon)
    if svg_data:
        cache_key = f"map_{country_code.lower()}"
        cached = get_cached(cache_key)
        if cached is not None and isinstance(cached, str):
            return str(cached)

        svg_encoded = base64.b64encode(svg_data.encode("utf-8")).decode("utf-8")
        data_uri = f"data:image/svg+xml;base64,{svg_encoded}"
        set_cached(cache_key, data_uri)
        return data_uri

    return None

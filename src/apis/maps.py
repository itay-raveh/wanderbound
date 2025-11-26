"""Country map generation and dot positioning."""

import base64
import json
from pathlib import Path
from typing import Any

import geopandas as gpd
from lxml import etree
from shapely.geometry import MultiPolygon, Point, Polygon

from ..logger import get_logger
from ..settings import get_settings
from .cache import CACHE_DIR, get_cached, set_cached

logger = get_logger(__name__)

_COUNTRY_BOUNDS: dict[str, Any] | None = None


def _remove_xml_declarations(svg_data: str) -> str:
    """Remove XML declaration and DOCTYPE from SVG to avoid DTD fetching.

    Args:
        svg_data: Raw SVG string.

    Returns:
        Cleaned SVG string without XML declarations.
    """
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
    """Parse SVG string using lxml."""
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
            country_gdf = world[world["ADMIN"].str.contains(country_name, case=False, na=False)]
        if not country_gdf.empty:
            return country_gdf

    # Try direct ADMIN match with country code as fallback
    if "ADMIN" in world.columns:
        country_gdf = world[world["ADMIN"].str.contains(country_code_lower, case=False, na=False)]
        if not country_gdf.empty:
            return country_gdf

    return None


def _geometry_to_svg_path(geometry: Any) -> str:
    """Convert Shapely geometry to SVG path data string.

    Args:
        geometry: Shapely geometry (Polygon, MultiPolygon, etc.)

    Returns:
        SVG path data string (d attribute value)
    """
    if geometry.is_empty:
        return ""

    if isinstance(geometry, Polygon):
        # Exterior ring
        coords = list(geometry.exterior.coords)
        if len(coords) < 2:
            return ""

        path_parts = [f"M {coords[0][0]},{coords[0][1]}"]
        for coord in coords[1:]:
            path_parts.append(f"L {coord[0]},{coord[1]}")
        path_parts.append("Z")

        # Interior rings (holes)
        for interior in geometry.interiors:
            coords = list(interior.coords)
            if len(coords) >= 2:
                path_parts.append(f"M {coords[0][0]},{coords[0][1]}")
                for coord in coords[1:]:
                    path_parts.append(f"L {coord[0]},{coord[1]}")
                path_parts.append("Z")

        return " ".join(path_parts)

    elif isinstance(geometry, MultiPolygon):
        # Combine all polygons
        paths = []
        for poly in geometry.geoms:
            path = _geometry_to_svg_path(poly)
            if path:
                paths.append(path)
        return " ".join(paths)

    else:
        # Fallback: try to get coordinates
        try:
            coords = list(geometry.coords)
            if len(coords) < 2:
                return ""
            path_parts = [f"M {coords[0][0]},{coords[0][1]}"]
            for coord in coords[1:]:
                path_parts.append(f"L {coord[0]},{coord[1]}")
            if geometry.is_closed:
                path_parts.append("Z")
            return " ".join(path_parts)
        except (AttributeError, TypeError):
            return ""


def _generate_svg_plot(gdf: Any, width: int, height: int) -> tuple[str, list[float], Any]:
    """Generate SVG plot from GeoDataFrame without matplotlib.

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
    root.set("viewBox", f"{min_x} {min_y} {viewbox_width} {viewbox_height}")
    root.set("xmlns", svg_ns)

    # Create group for paths
    group = etree.SubElement(root, f"{{{svg_ns}}}g")
    group.set("fill", "#ffffff")
    group.set("stroke", "none")

    # Convert each geometry to SVG path
    for _idx, row in gdf_proj.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty:
            continue

        path_data = _geometry_to_svg_path(geometry)
        if path_data:
            path_elem = etree.SubElement(group, f"{{{svg_ns}}}path")
            path_elem.set("d", path_data)

    # Convert to string
    svg_data_str = etree.tostring(root, encoding="unicode", pretty_print=False)
    svg_data: str = str(svg_data_str)  # Ensure it's a string for type checking

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

    svg_str = etree.tostring(root, encoding="unicode", pretty_print=False)
    return str(svg_str)


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

    # Generate geo-calibrated SVG
    svg_data = _generate_geo_calibrated_svg(country_code)
    if svg_data:
        set_cached(cache_key_svg, svg_data)
        return svg_data

    logger.warning(f"Failed to generate geo-calibrated SVG for {country_code}")
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
                                proj_bounds = [float(x) for x in proj_bounds_str.split(",")]
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

    # Fallback to country bounds if geo-calibrated data is not available
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

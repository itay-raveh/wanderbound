"""SVG map generation from Natural Earth data."""

import asyncio
from typing import TYPE_CHECKING, cast

import geopandas as gpd
from lxml import etree
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from src.core.logger import get_logger
from src.core.settings import settings
from src.services.utils import APIClient

if TYPE_CHECKING:
    from geopandas import GeoDataFrame

logger = get_logger(__name__)


async def _load_natural_earth_data(client: APIClient) -> "GeoDataFrame":
    """Load Natural Earth GeoJSON data from cache or download it."""
    ne_50m_url = settings.natural_earth_geojson_url
    cache_key_data = "ne_50m_admin_0_countries"

    # We use the cache directory defined in settings
    cache_file = settings.file.cache_dir / f"{cache_key_data}.geojson"

    if cache_file.exists():
        try:
            return await asyncio.to_thread(gpd.read_file, str(cache_file))
        except Exception as e:  # noqa: BLE001
            logger.warning("Cached map data corrupt, re-downloading: %s", e)

    logger.info("Downloading Natural Earth 50m data...")
    try:
        # Ensure cache directory exists
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        content = await client.get_content(ne_50m_url)
        with cache_file.open("wb") as f:
            f.write(content)

        return await asyncio.to_thread(gpd.read_file, str(cache_file))
    except (OSError, ValueError) as e:
        logger.warning("Failed to download Natural Earth data: %s", e)
        # Fallback to low-res if download fails
        logger.warning("Falling back to low-resolution map data")
        # geopandas.datasets is deprecated but available at runtime.
        datasets = getattr(gpd, "datasets")  # noqa: B009
        return await asyncio.to_thread(gpd.read_file, datasets.get_path("naturalearth_lowres"))


def _find_country_in_geodataframe(world: "GeoDataFrame", country_code_lower: str) -> "GeoDataFrame":
    """Find country geometry in the world dataset."""
    country_code_upper = country_code_lower.upper()

    # Try to find country by ISO_A2 code first (available in NE 50m)
    if "ISO_A2" in world.columns:
        country = world[world["ISO_A2"] == country_code_upper]
        if not country.empty:
            return country

    # Try ISO_A3 if A2 fails or not present (lowres has iso_a3)
    if "iso_a3" in world.columns:
        # We'd need A3 code here. For now, we might miss if we only have A2.
        # But NE 50m has ISO_A2, so we should be good if download works.
        pass

    # Fallback to ADMIN/name matching
    name_col = "ADMIN" if "ADMIN" in world.columns else "name"
    if name_col in world.columns:
        # Exact match
        country = world[world[name_col].str.lower() == country_code_lower]
        if not country.empty:
            return country

        # Contains match
        country = world[world[name_col].str.contains(country_code_lower, case=False, na=False)]
        if not country.empty:
            return country

    logger.warning("Country code '%s' not found in map data", country_code_lower)
    raise ValueError(f"Country '{country_code_lower}' not found in map data")


def _coords_to_svg_path(
    coords: list[tuple[float, float]], flip_y: tuple[float, float] | None = None
) -> str:
    """Convert a list of coordinates to an SVG path string."""
    if not coords:
        return ""

    path_cmds = []

    # If flip_y is provided (height, min_y), we flip the Y coordinate
    # SVG Y grows downwards, Geo Y (latitude) grows upwards.
    # We need to map [min_y, max_y] to [height, 0]

    for i, (x, y) in enumerate(coords):
        cmd = "M" if i == 0 else "L"
        if flip_y:
            # Actually, standard projection handling is better.
            # But here we assume the coordinates are already projected or we just plot them.
            # But Y needs flipping.
            pass

        path_cmds.append(f"{cmd} {x} {y}")

    path_cmds.append("Z")  # Close path
    return " ".join(path_cmds)


def _polygon_to_svg_path(polygon: Polygon, flip_y: tuple[float, float] | None = None) -> str:
    """Convert a shapely Polygon to SVG path."""
    # Exterior
    path = _coords_to_svg_path(
        cast("list[tuple[float, float]]", list(polygon.exterior.coords)), flip_y
    )

    for interior in polygon.interiors:
        path += " " + _coords_to_svg_path(
            cast("list[tuple[float, float]]", list(interior.coords)), flip_y
        )

    return path


def _multipolygon_to_svg_path(
    multipolygon: MultiPolygon, flip_y: tuple[float, float] | None = None
) -> str:
    """Convert a shapely MultiPolygon to SVG path."""
    paths = [_polygon_to_svg_path(polygon, flip_y) for polygon in multipolygon.geoms]
    return " ".join(paths)


def _geometry_to_svg_path(geometry: BaseGeometry, flip_y: tuple[float, float] | None = None) -> str:
    """Convert a shapely geometry to SVG path."""
    if isinstance(geometry, Polygon):
        return _polygon_to_svg_path(geometry, flip_y)
    if isinstance(geometry, MultiPolygon):
        return _multipolygon_to_svg_path(geometry, flip_y)
    return ""


def _generate_svg_plot(
    gdf: "GeoDataFrame", max_dimension: int
) -> tuple[etree._Element, list[float], str]:
    """Generate an SVG plot from a GeoDataFrame.

    Args:
        gdf: GeoDataFrame containing the country geometry.
        max_dimension: Maximum dimension (width or height) in pixels.

    Returns:
        tuple: (svg_root_element, bounds, crs_string)
    """
    # Get bounds
    minx, miny, maxx, maxy = gdf.total_bounds

    # Calculate aspect ratio to fit in width/height
    geo_width = maxx - minx
    geo_height = maxy - miny

    # Add some padding (5%)
    padding_x = geo_width * 0.05
    padding_y = geo_height * 0.05

    minx -= padding_x
    maxx += padding_x
    miny -= padding_y
    maxy += padding_y

    # Calculate dimensions and scale to fit max_dimension
    # We want the larger dimension to be exactly max_dimension
    # and the other dimension to scale accordingly.
    scale = max_dimension / geo_width if geo_width > geo_height else max_dimension / geo_height

    # Calculate exact pixel dimensions
    width = scale * geo_width
    height = scale * geo_height

    # Create SVG structure
    svg_ns = "http://www.w3.org/2000/svg"
    nsmap = {None: svg_ns}
    root = etree.Element(f"{{{svg_ns}}}svg", nsmap=nsmap)

    # Set viewBox to match the exact dimensions
    root.set("width", f"{width:.2f}")
    root.set("height", f"{height:.2f}")
    root.set("viewBox", f"0 0 {width:.2f} {height:.2f}")

    # Translation
    # We want minx * scale + tx = 0  => tx = -minx * scale
    # We want miny * -scale + ty = height => ty = height + miny * scale

    tx = -minx * scale
    ty = height + miny * scale

    group = cast("etree._Element", etree.SubElement(root, f"{{{svg_ns}}}g"))  # noqa: SLF001
    group.set("transform", f"translate({tx},{ty}) scale({scale},{-scale})")

    # Add path
    # We combine all geometries into one path for simplicity
    path_d = ""
    for _, row in gdf.iterrows():
        path_d += _geometry_to_svg_path(row.geometry) + " "

    path_elem = cast("etree._Element", etree.SubElement(group, f"{{{svg_ns}}}path"))  # noqa: SLF001
    path_elem.set("d", path_d.strip())
    path_elem.set("fill", settings.map.default_fill_color)
    path_elem.set("stroke", "none")

    # Return bounds and CRS for calibration
    bounds = [float(x) for x in [minx, miny, maxx, maxy]]
    crs = str(gdf.crs) if gdf.crs else "EPSG:4326"

    return root, bounds, crs


async def generate_geo_calibrated_svg(
    client: APIClient, country_code: str, max_dimension: int = 800
) -> str:
    """Generate a geo-calibrated SVG map for a country."""
    try:
        world = await _load_natural_earth_data(client)

        # CPU-bound: finding country and generating SVG
        def _generate() -> str:
            country_gdf = _find_country_in_geodataframe(world, country_code.lower())

            # Reproject to Web Mercator for better visual appearance (avoids "squished" look)
            # EPSG:3857 is standard for web maps
            if country_gdf.crs:
                country_gdf = country_gdf.to_crs("EPSG:3857")

            # Generate SVG plot
            svg_root, bounds, crs = _generate_svg_plot(country_gdf, max_dimension=max_dimension)

            # Add geo-calibration attributes to the root element
            svg_root.set("data-geo-bounds", ",".join(map(str, bounds)))
            svg_root.set("data-proj-bounds", ",".join(map(str, bounds)))  # Same for unprojected
            svg_root.set("data-crs", crs)

            # Serialize to string
            return str(etree.tostring(svg_root, encoding="unicode", pretty_print=False))

        return await asyncio.to_thread(_generate)

    except Exception as e:
        logger.exception("Failed to generate map for %s", country_code)
        raise ValueError(f"Map generation failed: {e}") from e

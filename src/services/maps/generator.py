"""SVG map generation from Natural Earth data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree
from shapely.geometry import MultiPolygon, Polygon

from src.core.logger import get_logger

if TYPE_CHECKING:
    from geopandas import GeoDataFrame
    from shapely.coords import CoordinateSequence
    from shapely.geometry.base import BaseGeometry

_ETREE_XML_PARSER = etree.XMLParser(
    recover=True,
    strip_cdata=False,
    no_network=True,  # Don't fetch external DTDs
)

logger = get_logger(__name__)


def _coords_to_svg_path(coords: CoordinateSequence) -> str:
    """Convert a list of coordinates to an SVG path string."""
    if not coords:
        return ""

    path_cmds: list[str] = []

    for i, (x, y) in enumerate(coords):
        cmd = "M" if i == 0 else "L"
        path_cmds.append(f"{cmd} {x} {y}")

    path_cmds.append("Z")

    return " ".join(path_cmds)


def _polygon_to_svg_path(polygon: Polygon) -> str:
    """Convert a shapely Polygon to SVG path."""
    paths = [_coords_to_svg_path(polygon.exterior.coords)]
    paths.extend(_coords_to_svg_path(hole.coords) for hole in polygon.interiors)
    return " ".join(paths)


def _multipolygon_to_svg_path(multipolygon: MultiPolygon) -> str:
    """Convert a shapely MultiPolygon to SVG path."""
    return " ".join(map(_polygon_to_svg_path, multipolygon.geoms))


def _geometry_to_svg_path(geometry: BaseGeometry) -> str:
    """Convert a shapely geometry to SVG path."""
    if isinstance(geometry, Polygon):
        return _polygon_to_svg_path(geometry)
    if isinstance(geometry, MultiPolygon):
        return _multipolygon_to_svg_path(geometry)
    return ""


def _generate_svg_plot(
    gdf: GeoDataFrame, max_dimension: int
) -> tuple[etree._Element, tuple[float, float, float, float]]:
    # Get bounds
    min_x, min_y, max_x, max_y = gdf.total_bounds

    # Calculate aspect ratio to fit in width/height
    geo_width = max_x - min_x
    geo_height = max_y - min_y

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
    root = etree.Element(f"{{{svg_ns}}}svg", nsmap=nsmap)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    # Set viewBox to match the exact dimensions
    root.set("width", f"{width:.2f}")
    root.set("height", f"{height:.2f}")
    root.set("viewBox", f"0 0 {width:.2f} {height:.2f}")

    tx = -min_x * scale
    ty = height + min_y * scale

    group = etree.SubElement(root, f"{{{svg_ns}}}g")
    group.set("transform", f"translate({tx},{ty}) scale({scale},{-scale})")

    # Add path
    # We combine all geometries into one path for simplicity
    path_d: list[str] = []
    for _, row in gdf.iterrows():
        path_d.append(_geometry_to_svg_path(row.geometry))  # pyright: ignore[reportAny]

    path_elem = etree.SubElement(group, f"{{{svg_ns}}}path")
    path_elem.set("d", " ".join(path_d).strip())
    path_elem.set("fill", "var(--text-primary)")
    path_elem.set("stroke", "none")

    return root, (min_x, min_y, max_x, max_y)


def generate_geo_calibrated_svg(
    world: GeoDataFrame, country_code: str, max_dimension: int = 800
) -> tuple[str, tuple[float, float, float, float]]:
    """Generate a geo-calibrated SVG map for a country."""
    # Find country by code and project to EPSG:3857 (2D Web Mercator)
    country_gdf = world[world["ISO_A2"] == country_code.upper()].to_crs("EPSG:3857")

    # Generate SVG
    svg_root, bounds = _generate_svg_plot(country_gdf, max_dimension=max_dimension)

    # Add geo-calibration attributes to the root element (so that it's cached)
    svg_root.set("data-bounds", ",".join(map(str, bounds)))

    # Serialize to string
    return str(etree.tostring(svg_root, encoding="unicode", pretty_print=False)), bounds

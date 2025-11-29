"""Coordinate calculation and dot positioning."""

from typing import cast

import geopandas as gpd
from lxml import etree
from shapely.geometry import Point

from .svg_utils import parse_svg_with_lxml


def _calculate_position_from_projected_bounds(
    lat: float, lon: float, proj_bounds: list[float], crs_str: str
) -> tuple[float, float]:
    """Calculate position using projected bounds and CRS."""
    point_geo = gpd.GeoDataFrame(geometry=[Point(lon, lat)], crs="EPSG:4326")
    point_proj = point_geo.to_crs(crs_str)

    geom = cast("Point", point_proj.geometry.iloc[0])
    proj_x = geom.x
    proj_y = geom.y

    proj_min_x, proj_min_y, proj_max_x, proj_max_y = proj_bounds
    proj_width = proj_max_x - proj_min_x
    proj_height = proj_max_y - proj_min_y

    # We assume valid bounds with non-zero dimensions
    x_ratio = (proj_x - proj_min_x) / proj_width
    y_ratio = (proj_max_y - proj_y) / proj_height

    x_percent = max(0, min(100, x_ratio * 100))
    y_percent = max(0, min(100, y_ratio * 100))

    return (x_percent, y_percent)


def _calculate_position_from_svg_root(
    root: etree._Element, lat: float, lon: float
) -> tuple[float, float]:
    """Calculate position from SVG root element using projected bounds."""
    # We expect these attributes to be present. If not, KeyError will be raised.
    proj_bounds_str = root.attrib["data-proj-bounds"]
    crs_str = root.attrib["data-crs"]

    proj_bounds = [float(x) for x in proj_bounds_str.split(",")]

    return _calculate_position_from_projected_bounds(lat, lon, proj_bounds, crs_str)


def get_country_map_dot_position(lat: float, lon: float, svg_data: str) -> tuple[float, float]:
    """Calculate the relative position (0-100%) of a location dot within a country map."""
    # We assume svg_data is valid XML/SVG
    root = parse_svg_with_lxml(svg_data)

    return _calculate_position_from_svg_root(root, lat, lon)

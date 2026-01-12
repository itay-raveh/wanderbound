"""Coordinate calculation and dot positioning."""

from collections.abc import Callable

from pyproj import Transformer

from .svg_utils import parse_svg_with_lxml

# Projects (lon , lat) pairs to web mercator
_transform: Callable[[float, float], tuple[float, float]] = Transformer.from_crs(
    "EPSG:4326", "EPSG:3857", always_xy=True
).transform


def get_country_map_dot_position(lon: float, lat: float, svg_data: str) -> tuple[float, float]:
    """Calculate the relative position (0-100%) of a location dot within a country map."""
    root = parse_svg_with_lxml(svg_data)

    min_x, min_y, max_x, max_y = [float(x) for x in str(root.attrib["data-bounds"]).split(",")]

    x, y = _transform(lon, lat)

    x_ratio = (x - min_x) / (max_x - min_x)
    y_ratio = (max_y - y) / (max_y - min_y)

    x_percent = 100 * max(0.0, min(x_ratio, 1))
    y_percent = 100 * max(0.0, min(y_ratio, 1))

    return x_percent, y_percent

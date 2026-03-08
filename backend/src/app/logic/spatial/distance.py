import math

import numpy as np
from numpy import float64
from numpy.typing import NDArray
import polars as pl

__all__ = ["geodist_2d", "geodist_3d"]

# Earth radius in meters
R = 6371000.0


# https://en.wikipedia.org/wiki/Haversine_formula#Formulation
def geodist_2d[T: NDArray[float64]](lats: T, lons: T) -> T:
    """Vectorized geodesic distance.

    Args:
        lats: Latitudes.
        lons: Longitudes.

    Returns:
        Distances (meters).
    """
    phi_1, phi_2 = np.radians(lats[:-1]), np.radians(lats[1:])
    lambda_1, lambda_2 = np.radians(lons[:-1]), np.radians(lons[1:])

    d_phi = phi_2 - phi_1
    d_lambda = lambda_2 - lambda_1

    a = np.sin(d_phi / 2) ** 2 + np.cos(phi_1) * np.cos(phi_2) * np.sin(d_lambda / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    return c * R  # pyright: ignore[reportReturnType]


def geodist_3d[T: NDArray[float64]](lats: T, lons: T, elevs: T) -> T:
    """Vectorized 3D distance (geodesic on xy, euclidian on z).

    Args:
        lats: Latitudes.
        lons: Longitudes.
        elevs: Elevations (meters).

    Returns:
        Distances (meters).
    """
    d_xy = geodist_2d(lats, lons)
    d_h = elevs[1:] - elevs[:-1]
    return np.sqrt(d_xy**2 + d_h**2)  # pyright: ignore[reportReturnType]



def haversine_expr_between(lat1: pl.Expr, lon1: pl.Expr, lat2: pl.Expr, lon2: pl.Expr) -> pl.Expr:
    """Calculates the 2D Haversine distance in meters between two pairs of coordinate expressions."""
    to_rad = math.pi / 180.0
    phi_1 = lat1 * to_rad
    phi_2 = lat2 * to_rad
    lambda_1 = lon1 * to_rad
    lambda_2 = lon2 * to_rad

    d_phi = phi_2 - phi_1
    d_lambda = lambda_2 - lambda_1

    a = (d_phi / 2).sin() ** 2 + phi_1.cos() * phi_2.cos() * (d_lambda / 2).sin() ** 2
    c = 2 * pl.arctan2(a.sqrt(), (1 - a).sqrt())

    return c * R

def haversine_expr(lat_col: str = "lats", lon_col: str = "lons") -> pl.Expr:
    """Calculates the 2D Haversine distance in meters to the previous row using pure Polars expressions."""
    c_r = haversine_expr_between(
        pl.col(lat_col).shift(1), pl.col(lon_col).shift(1),
        pl.col(lat_col), pl.col(lon_col)
    )
    return c_r.fill_null(0.0)

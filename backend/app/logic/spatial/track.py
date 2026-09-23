"""Prepare ordered GPS and step points for movement segmentation."""

import math
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Protocol, cast

import numpy as np
import polars as pl

from app.logic.spatial.geo import EARTH_RADIUS_KM
from app.logic.spatial.segment_rules import (
    _KM_PER_DEG,
    DENSIFY_MAX_SPEED_KMH,
    DENSIFY_RESOLUTION_KM,
    FLIGHT_MIN_DISTANCE_KM,
    FLIGHT_SPARSE_MIN_DISTANCE_KM,
    FLIGHT_SPARSE_MIN_SPEED_KMH,
    ISOLATED_POINT_MIN_DIST_KM,
    MAX_HIKE_GAP_H,
    NOISE_GAP_MAX_DIST_KM,
    SPIKE_MIN_DIST_KM,
    TELEPORT_MAX_SPEED_KMH,
)
from app.models.polarsteps import HasLatLon, Point


class _StepLike(Protocol):
    """Structural interface for step objects used by the segmentation pipeline."""

    @property
    def location(self) -> HasLatLon: ...
    @property
    def datetime(self) -> datetime: ...


def _merge_points(
    steps: Sequence[_StepLike], locations: Iterable[Point]
) -> pl.DataFrame:
    """Merge step pins and GPS fixes, keeping step pins at timestamp collisions."""
    points = [
        (
            Point(lat=s.location.lat, lon=s.location.lon, time=s.datetime.timestamp()),
            True,
        )
        for s in steps
    ]
    points.extend((point, False) for point in locations)
    points.sort(key=lambda row: row[0].time)

    merged: list[tuple[Point, bool]] = []
    previous_time: float | None = None
    for point, is_step in points:
        if previous_time is not None and point.time - previous_time <= 0.001:
            if is_step and not merged[-1][1]:
                merged[-1] = (point, True)
        else:
            merged.append((point, is_step))
        previous_time = point.time

    if not merged:
        return pl.DataFrame(
            schema={
                "lat": pl.Float64,
                "lon": pl.Float64,
                "time": pl.Float64,
                "is_step": pl.Boolean,
            }
        )
    return pl.DataFrame(
        {
            "lat": [point.lat for point, _ in merged],
            "lon": [point.lon for point, _ in merged],
            "time": [point.time for point, _ in merged],
            "is_step": [is_step for _, is_step in merged],
        }
    )


# https://en.wikipedia.org/wiki/Haversine_formula#Formulation
def _haversine_km(
    lat1: pl.Expr, lon1: pl.Expr, lat2: pl.Expr, lon2: pl.Expr
) -> pl.Expr:
    """Vectorized haversine on Polars expressions (not the scalar version in geo.py)."""
    to_rad = math.pi / 180.0
    phi_1 = lat1 * to_rad
    phi_2 = lat2 * to_rad
    lambda_1 = lon1 * to_rad
    lambda_2 = lon2 * to_rad

    d_phi = phi_2 - phi_1
    d_lambda = lambda_2 - lambda_1

    a = (d_phi / 2).sin() ** 2 + phi_1.cos() * phi_2.cos() * (d_lambda / 2).sin() ** 2
    c = 2 * pl.arctan2(a.sqrt(), (1 - a).sqrt())

    return c * EARTH_RADIUS_KM


def _add_edge_metrics(df: pl.DataFrame) -> pl.DataFrame:
    """Compute incoming edge metrics for each point.

    Each row describes the edge *arriving at* that row from the previous one.
    Row 0 has no incoming edge and gets zero metrics.
    """
    return df.with_columns(
        ((pl.col("time") - pl.col("time").shift(1)) / 3600.0)
        .fill_null(0.0)
        .alias("incoming_gap_h"),
        (
            _haversine_km(
                pl.col("lat").shift(1),
                pl.col("lon").shift(1),
                pl.col("lat"),
                pl.col("lon"),
            ).fill_null(0.0)
        ).alias("incoming_dist_km"),
    ).with_columns(
        pl.when(pl.col("incoming_gap_h") > 0)
        .then(pl.col("incoming_dist_km") / pl.col("incoming_gap_h"))
        .otherwise(0.0)
        .alias("incoming_speed_kmh"),
    )


def _edge_frame(points: pl.DataFrame) -> pl.DataFrame:
    """One row per movement, keyed by its start and end point IDs."""
    return points.slice(1).select(
        (pl.col("point_id") - 1).alias("start_point_id"),
        pl.col("point_id").alias("end_point_id"),
        pl.col("incoming_gap_h").alias("gap_h"),
        pl.col("incoming_dist_km").alias("dist_km"),
        pl.col("incoming_speed_kmh").alias("speed_kmh"),
    )


def _deg_dist(shift: int = 1) -> pl.Expr:
    """Degree-distance to the point ``shift`` rows back."""
    lon_delta = (pl.col("lon") - pl.col("lon").shift(shift) + 180) % 360 - 180
    return ((pl.col("lat") - pl.col("lat").shift(shift)) ** 2 + lon_delta**2).sqrt()


def _remove_stale_points(df: pl.DataFrame, is_step: pl.Expr) -> pl.DataFrame:
    """Drop stale GPS points only when surrounding points confirm the route."""
    if df.height < 4:
        return df

    lat, lon, time = pl.col("lat"), pl.col("lon"), pl.col("time")

    def distance(first: int, second: int) -> pl.Expr:
        return _haversine_km(
            lat.shift(first), lon.shift(first), lat.shift(second), lon.shift(second)
        )

    next_speed = distance(0, -1) / ((time.shift(-1) - time) / 3600)
    confirmed_return = (
        ~is_step
        & (distance(1, 0) > SPIKE_MIN_DIST_KM)
        & (distance(1, -1) < NOISE_GAP_MAX_DIST_KM)
        & (distance(1, -2) < NOISE_GAP_MAX_DIST_KM)
        & (next_speed > TELEPORT_MAX_SPEED_KMH)
    ).fill_null(value=False)
    df = df.filter(~confirmed_return)

    if df.height < 4:
        return df

    bridge_dist = distance(1, -1)
    bridge_speed = bridge_dist / ((time.shift(-1) - time.shift(1)) / 3600)
    road_bridge = (
        (bridge_speed < FLIGHT_SPARSE_MIN_SPEED_KMH)
        & (bridge_dist > ISOLATED_POINT_MIN_DIST_KM)
        & (bridge_dist < FLIGHT_MIN_DISTANCE_KM)
        & (distance(1, 0) < NOISE_GAP_MAX_DIST_KM)
    )
    flight_bridge = (
        (bridge_speed >= FLIGHT_SPARSE_MIN_SPEED_KMH)
        & (bridge_dist >= FLIGHT_SPARSE_MIN_DISTANCE_KM)
        & (distance(1, 0) > ISOLATED_POINT_MIN_DIST_KM)
        & (distance(2, 1) < NOISE_GAP_MAX_DIST_KM)
    )
    # A stale origin point can make a valid arrival look like a teleport.
    late_origin = (
        ~is_step
        & (distance(-1, -2) < NOISE_GAP_MAX_DIST_KM)
        & (road_bridge | flight_bridge)
        & (bridge_speed <= TELEPORT_MAX_SPEED_KMH)
        & (next_speed > TELEPORT_MAX_SPEED_KMH)
    ).fill_null(value=False)
    return df.filter(~late_origin)


def _remove_gps_noise(df: pl.DataFrame) -> pl.DataFrame:
    """Drop confirmed stale points, teleports, and spikes.

    Step waypoints are always kept.
    """
    has_is_step = "is_step" in df.columns
    is_step = pl.col("is_step") if has_is_step else pl.lit(value=False)
    keep_cols = ["lat", "lon", "time"] + (["is_step"] if has_is_step else [])

    if df.height < 2:
        return df

    df = _remove_stale_points(df, is_step)

    # Teleports: apparent speed > 1000 km/h
    dt = ((pl.col("time") - pl.col("time").shift(1)) / 3600.0).fill_null(1.0)
    speed = _deg_dist().fill_null(0.0) / dt
    lat, lon = pl.col("lat"), pl.col("lon")
    # A distant step pin must not erase GPS fixes supported on both sides.
    supported_after_step = (
        ~is_step
        & is_step.shift(1, fill_value=False)
        & ~is_step.shift(2, fill_value=False)
        & ~is_step.shift(-1, fill_value=False)
        & (_haversine_km(lat.shift(2), lon.shift(2), lat, lon) < NOISE_GAP_MAX_DIST_KM)
        & (
            _haversine_km(lat, lon, lat.shift(-1), lon.shift(-1))
            < NOISE_GAP_MAX_DIST_KM
        )
        & (
            _haversine_km(lat.shift(1), lon.shift(1), lat, lon)
            > ISOLATED_POINT_MIN_DIST_KM
        )
    ).fill_null(value=False)
    # Keep the good return fix when the previous raw point was a teleport.
    return_after_teleport = (
        ~is_step.shift(1, fill_value=False)
        & (speed.shift(1) > TELEPORT_MAX_SPEED_KMH / _KM_PER_DEG)
        & (_haversine_km(lat.shift(2), lon.shift(2), lat, lon) < NOISE_GAP_MAX_DIST_KM)
    ).fill_null(value=False)
    df = df.filter(
        is_step
        | supported_after_step
        | return_after_teleport
        | (speed <= TELEPORT_MAX_SPEED_KMH / _KM_PER_DEG)
    )

    if df.height < 3:
        return df.select(keep_cols)

    # Spikes: far from prev neighbor but prev->next is short (triangle inequality)
    dd = _deg_dist().fill_null(0.0)
    across_lon = (lon.shift(1) - lon.shift(-1) + 180) % 360 - 180
    across = ((lat.shift(1) - lat.shift(-1)) ** 2 + across_lon**2).sqrt()
    spike = (
        ~is_step & (dd > SPIKE_MIN_DIST_KM / _KM_PER_DEG) & (across < dd * 0.5)
    ).fill_null(value=False)
    df = df.filter(~spike)

    return df.select(keep_cols)


def _densify_hike_edges(df: pl.DataFrame) -> pl.DataFrame:
    """Linearly interpolate slow edges to ~15 m spacing.

    Only densifies edges at hike speed, within gap limit, and sparser than
    the target resolution.  Vectorized via NumPy repeat/cumsum.

    Caller must re-run _add_edge_metrics afterwards.
    """
    lats = df["lat"].to_numpy()
    lons = df["lon"].to_numpy()
    times = df["time"].to_numpy()
    is_steps = df["is_step"].to_numpy()

    if len(lats) < 2:
        return df

    dists = df["incoming_dist_km"].to_numpy()[1:]
    dts = df["incoming_gap_h"].to_numpy()[1:]
    speeds = df["incoming_speed_kmh"].to_numpy()[1:]

    should_densify = (
        (speeds <= DENSIFY_MAX_SPEED_KMH)
        & (dists > DENSIFY_RESOLUTION_KM)
        & (dts < MAX_HIKE_GAP_H)
    )

    n_pts: np.typing.NDArray[np.int_] = np.where(
        should_densify, np.ceil(dists / DENSIFY_RESOLUTION_KM).astype(int), 1
    )

    edge_idx = np.repeat(np.arange(len(n_pts)), n_pts)
    cum_before = np.concatenate([[0], n_pts[:-1].cumsum()])
    local_step = np.arange(cast("np.int_", n_pts.sum())) - cum_before[edge_idx]
    frac = (local_step + 1) / n_pts[edge_idx]

    i0, i1 = edge_idx, edge_idx + 1
    lon_delta = lons[i1] - lons[i0]
    lon_delta = np.where(
        lon_delta > 180,
        lon_delta - 360,
        np.where(lon_delta < -180, lon_delta + 360, lon_delta),
    )
    interpolated_lons = lons[i0] + lon_delta * frac
    interpolated_lons = np.where(
        interpolated_lons > 180,
        interpolated_lons - 360,
        np.where(interpolated_lons < -180, interpolated_lons + 360, interpolated_lons),
    )
    interpolated_lons = np.where(
        local_step + 1 == n_pts[edge_idx], lons[i1], interpolated_lons
    )
    return pl.DataFrame(
        {
            "lat": np.concatenate([[lats[0]], lats[i0] + (lats[i1] - lats[i0]) * frac]),
            "lon": np.concatenate([[lons[0]], interpolated_lons]),
            "time": np.concatenate(
                [[times[0]], times[i0] + (times[i1] - times[i0]) * frac]
            ),
            "is_step": np.concatenate(
                [[is_steps[0]], is_steps[i1] & (local_step + 1 == n_pts[edge_idx])]
            ),
        }
    )


def _ingest(steps: Sequence[_StepLike], locations: Iterable[Point]) -> pl.DataFrame:
    """Merge steps + GPS into a clean, densified DataFrame with edge metrics."""
    df = _merge_points(steps, locations)
    if df.height == 0:
        return df

    df = _remove_gps_noise(df)
    df = _add_edge_metrics(df)
    df = _densify_hike_edges(df)
    return _add_edge_metrics(df)

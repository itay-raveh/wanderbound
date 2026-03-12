"""Segment a Polarsteps GPS track into typed movement segments.

Pipeline: ingest → label → absorb → validate → emit.

  1. Ingest    Merge steps + GPS, remove teleports/spikes, densify slow edges.
  2. Label     Classify edges as hike / flight / other by speed + gap.
  3. Absorb    Fold GPS noise, overnight camps, and blackouts back into hikes.
  4. Validate  Drop undersized hikes (< 2 h, < 2 km, < 1 km displacement)
               and short flights (< 100 km).  Rejects become "other".
  5. Emit      RDP-simplify, resolve "other" → walking/driving, stitch gaps.

DataFrame columns through the pipeline::

    lat, lon, time   coordinates + Unix timestamp
    gap_h            hours since previous point
    dist_km          haversine km from previous point
    speed_kmh        dist_km / gap_h
    is_step          True for step waypoints (immune to noise removal)
    mode             hike | flight | other (after label + absorb)
    segment_id       RLE group ID on mode
    final_mode       after validation (undersized → other)
    output_id        RLE group ID on final_mode
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import TYPE_CHECKING, cast

import numpy as np
import polars as pl
from pydantic import BaseModel

from app.core.logging import config_logger
from app.models.trips import Point

from .simplify import rdp_mask

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from app.models.db import Step


logger = config_logger(__name__)

# ── Edge classification ───────────────────────────────────────────────────────
# GPS underreports speed on winding trails (~6.5 km/h vs ~8 km/h actual).
# Motorized transport (tuk-tuks, minibuses) typically exceeds this even in traffic.
HIKE_MAX_SPEED_KMH = 6.5
FLIGHT_MIN_SPEED_KMH = 200.0

# ── Hike validity (all three must pass, otherwise downgraded to "walking") ───
# Displacement = max distance from start, filters hostel GPS drift.
HIKE_MIN_DURATION_H = 2.0
HIKE_MIN_DISTANCE_KM = 2.0
HIKE_MIN_DISPLACEMENT_KM = 1.0

FLIGHT_MIN_DISTANCE_KM = 100.0
MAX_HIKE_GAP_H = 4.0

# ── GPS noise ────────────────────────────────────────────────────────────────
# > 1000 km/h = impossible GPS jump.  Step waypoints are immune.
TELEPORT_MAX_SPEED_KMH = 1000.0

# ── Densification ────────────────────────────────────────────────────────────
# Interpolate slow edges to ~15 m spacing so sparse GPS doesn't hide short hikes.
DENSIFY_MAX_SPEED_KMH = 5.0
DENSIFY_RESOLUTION_KM = 0.015

# ── Absorption pass 1: noise gaps ────────────────────────────────────────────
# Short "other" between two hikes at hike speed → fold back into hike.
# Requires a following hike anchor to avoid absorbing post-hike hotel drift.
NOISE_GAP_MAX_DIST_KM = 4.0
NOISE_GAP_MAX_H = 3.0

# ── Absorption pass 2: camps + blackouts ─────────────────────────────────────

# Camp: GPS barely moved overnight.  No speed check — tight distance cap
# prevents transport; a speed check would reject walks-to-trailhead.
CAMP_GAP_MAX_DIST_KM = 1.0
CAMP_GAP_MAX_H = 20.0

# Blackout: phone stopped logging mid-hike.  Absorbed at hike speed.
# Short (< 6 h): only following anchor needed.  Long (6-24 h): both anchors,
# to avoid merging evening city walk with next morning's hike.
# Distance caps: short can cover more (bus to trailhead); long with significant
# distance likely includes driving (real overnight has only GPS drift).
BLACKOUT_GAP_SHORT_MAX_H = 6.0
BLACKOUT_GAP_LONG_MAX_H = 24.0
BLACKOUT_GAP_SHORT_MAX_DIST_KM = 10.0
BLACKOUT_GAP_LONG_MAX_DIST_KM = 4.0

# Anchor: min hike run adjacent to a gap.  Lower than HIKE_MIN_DURATION_H
# so a 1.5 h fragment before a mountain camp still qualifies.
HIKE_ANCHOR_MIN_H = 1.5
# Camp merge needs a lower bar on the *preceding* hike to guard against
# a brief evening city walk anchoring an overnight merge.
CAMP_PREV_ANCHOR_MIN_H = 1.0

RDP_EPSILON_DEG = 0.001  # RDP simplification tolerance (degrees)


class SegmentKind(StrEnum):
    flight = "flight"
    hike = "hike"
    walking = "walking"
    driving = "driving"


class SegmentData(BaseModel):
    kind: SegmentKind
    points: list[Point]


# ═══════════════════════════════════════════════════════════════════
#  Stage 1: Ingest
# ═══════════════════════════════════════════════════════════════════


def _points_to_df(pts: Iterable[Point]) -> pl.DataFrame:
    """Convert an iterable of Points to a column-oriented Polars DataFrame."""
    points = list(pts)
    if not points:
        return pl.DataFrame(
            schema={"lat": pl.Float64, "lon": pl.Float64, "time": pl.Float64}
        )
    return pl.DataFrame(
        {
            "lat": [p.lat for p in points],
            "lon": [p.lon for p in points],
            "time": [p.time for p in points],
        }
    )


_EARTH_RADIUS_KM = 6371.0


# https://en.wikipedia.org/wiki/Haversine_formula#Formulation
def _haversine_km(
    lat1: pl.Expr, lon1: pl.Expr, lat2: pl.Expr, lon2: pl.Expr
) -> pl.Expr:
    to_rad = math.pi / 180.0
    phi_1 = lat1 * to_rad
    phi_2 = lat2 * to_rad
    lambda_1 = lon1 * to_rad
    lambda_2 = lon2 * to_rad

    d_phi = phi_2 - phi_1
    d_lambda = lambda_2 - lambda_1

    a = (d_phi / 2).sin() ** 2 + phi_1.cos() * phi_2.cos() * (d_lambda / 2).sin() ** 2
    c = 2 * pl.arctan2(a.sqrt(), (1 - a).sqrt())

    return c * _EARTH_RADIUS_KM


def _add_edge_metrics(df: pl.DataFrame) -> pl.DataFrame:
    """Compute per-edge gap_h, dist_km, and speed_kmh.

    Each row describes the edge *arriving at* that row from the previous one.
    Row 0 always gets gap_h=0, dist_km=0, speed_kmh=0.
    """
    return df.with_columns(
        ((pl.col("time") - pl.col("time").shift(1)) / 3600.0)
        .fill_null(0.0)
        .alias("gap_h"),
        (
            _haversine_km(
                pl.col("lat").shift(1),
                pl.col("lon").shift(1),
                pl.col("lat"),
                pl.col("lon"),
            ).fill_null(0.0)
        ).alias("dist_km"),
    ).with_columns(
        pl.when(pl.col("gap_h") > 0)
        .then(pl.col("dist_km") / pl.col("gap_h"))
        .otherwise(0.0)
        .alias("speed_kmh"),
    )


def _dedup_by_time(df: pl.DataFrame) -> pl.DataFrame:
    """Drop points within 1 ms of the previous (step/GPS collisions)."""
    return df.filter(
        (pl.col("time") - pl.col("time").shift(1)).abs().fill_null(1) > 0.001
    )


def _deg_dist(shift: int = 1) -> pl.Expr:
    """Euclidean degree-distance to the point ``shift`` rows back (1° ≈ 80 km)."""
    return (
        (pl.col("lat") - pl.col("lat").shift(shift)) ** 2
        + (pl.col("lon") - pl.col("lon").shift(shift)) ** 2
    ).sqrt()


def _remove_gps_noise(df: pl.DataFrame) -> pl.DataFrame:
    """Drop teleports (impossible speed) and spikes (triangle inequality).

    Step waypoints are always kept.
    """
    has_is_step = "is_step" in df.columns
    is_step = pl.col("is_step") if has_is_step else pl.lit(value=False)
    keep_cols = ["lat", "lon", "time"] + (["is_step"] if has_is_step else [])

    if df.height < 2:
        return df

    # Teleports: apparent speed > 1000 km/h
    dt = ((pl.col("time") - pl.col("time").shift(1)) / 3600.0).fill_null(1.0)
    speed = _deg_dist().fill_null(0.0) / dt
    df = df.filter(is_step | (speed <= TELEPORT_MAX_SPEED_KMH / 80.0))

    if df.height < 3:
        return df.select(keep_cols)

    # Spikes: far from prev neighbor but prev→next is short (triangle inequality)
    dd = _deg_dist().fill_null(0.0)
    across = (
        (pl.col("lat").shift(1) - pl.col("lat").shift(-1)) ** 2
        + (pl.col("lon").shift(1) - pl.col("lon").shift(-1)) ** 2
    ).sqrt()
    spike = (~is_step & (dd > 0.5 / 80.0) & (across < dd * 0.5)).fill_null(value=False)
    df = df.filter(~spike)

    return df.select(keep_cols)


def _densify_hike_edges(df: pl.DataFrame) -> pl.DataFrame:
    """Linearly interpolate slow edges to ~15 m spacing.

    Only densifies edges at hike speed, within gap limit, and sparser than
    the target resolution.  Vectorized via NumPy repeat/cumsum.

    Outputs only lat/lon/time — caller must re-run _add_edge_metrics and
    re-mark step rows afterwards.
    """
    lats = df["lat"].to_numpy()
    lons = df["lon"].to_numpy()
    times = df["time"].to_numpy()

    if len(lats) < 2:
        return df

    dists = df["dist_km"].to_numpy()[1:]
    dts = df["gap_h"].to_numpy()[1:]
    speeds = df["speed_kmh"].to_numpy()[1:]

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
    return pl.DataFrame(
        {
            "lat": np.concatenate([[lats[0]], lats[i0] + (lats[i1] - lats[i0]) * frac]),
            "lon": np.concatenate([[lons[0]], lons[i0] + (lons[i1] - lons[i0]) * frac]),
            "time": np.concatenate(
                [[times[0]], times[i0] + (times[i1] - times[i0]) * frac]
            ),
        }
    )


def _ingest(steps: Sequence[Step], locations: Iterable[Point]) -> pl.DataFrame:
    """Merge steps + GPS into a clean, densified DataFrame with edge metrics."""
    step_pts = sorted(
        Point(lat=s.location.lat, lon=s.location.lon, time=s.datetime.timestamp())
        for s in steps
    )
    step_times = [p.time for p in step_pts]

    df = _points_to_df(sorted([*step_pts, *locations]))
    if df.height == 0:
        return df

    df = _dedup_by_time(df)
    # Mark steps before noise removal so they survive
    df = df.with_columns(pl.col("time").is_in(step_times).alias("is_step"))
    df = _remove_gps_noise(df)
    df = _add_edge_metrics(df)
    df = _densify_hike_edges(df)
    df = _add_edge_metrics(df)
    # Re-mark: densified rows aren't steps
    return df.with_columns(pl.col("time").is_in(step_times).alias("is_step"))


# ═══════════════════════════════════════════════════════════════════
#  Stage 2: Label edges
# ═══════════════════════════════════════════════════════════════════


def _label_edges(df: pl.DataFrame) -> pl.DataFrame:
    """Classify each edge as flight / hike / other by speed and gap.

    Flight wins over hike (both takeoff + landing edges are marked).
    Step-adjacent edges bypass the speed check — the step anchors the path
    even when GPS was silent.
    """
    is_flight_edge = pl.col("speed_kmh") >= FLIGHT_MIN_SPEED_KMH
    flight_mask = is_flight_edge | is_flight_edge.shift(-1, fill_value=False)

    step_adjacent = pl.col("is_step") | pl.col("is_step").shift(1, fill_value=False)
    within_gap_limit = pl.col("gap_h") < pl.lit(MAX_HIKE_GAP_H)
    at_hike_speed = pl.col("speed_kmh") <= HIKE_MAX_SPEED_KMH
    is_hike_edge = (at_hike_speed | (step_adjacent & ~flight_mask)) & within_gap_limit

    return df.with_columns(
        pl.when(flight_mask)
        .then(pl.lit("flight"))
        .when(is_hike_edge)
        .then(pl.lit("hike"))
        .otherwise(pl.lit("other"))
        .alias("mode"),
    )


# ═══════════════════════════════════════════════════════════════════
#  Stage 3: Absorb gaps
# ═══════════════════════════════════════════════════════════════════


def _run_stats(df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """RLE-group by mode and compute per-run duration, distance, speed."""
    df = df.with_columns(pl.col("mode").rle_id().alias("run_id"))
    stats = (
        df.group_by("run_id")
        .agg(
            pl.col("mode").first().alias("run_mode"),
            pl.col("gap_h").sum().alias("run_h"),
            pl.col("dist_km").sum().alias("run_dist_km"),
        )
        .sort("run_id")
        .with_columns(
            pl.when(pl.col("run_h") > 0)
            .then(pl.col("run_dist_km") / pl.col("run_h"))
            .otherwise(0.0)
            .alias("run_speed_kmh"),
        )
    )
    return df, stats


def _absorb_noise_gaps(df: pl.DataFrame) -> pl.DataFrame:
    """Fold short GPS-dropout gaps (< 4 km, < 3 h, hike speed) back into hike.

    Requires a following hike anchor so we don't absorb post-hike drift.
    Nulls the gap's mode and forward-fills from the preceding hike.
    """
    df, stats = _run_stats(df)
    stats = stats.with_columns(
        pl.col("run_h").shift(-1).fill_null(0.0).alias("next_run_h"),
    )
    df = df.join(stats, on="run_id")

    is_noise_gap = (
        (pl.col("run_mode") == "other")
        & (pl.col("run_dist_km") < NOISE_GAP_MAX_DIST_KM)
        & (pl.col("run_h") < NOISE_GAP_MAX_H)
        & (pl.col("run_speed_kmh") <= HIKE_MAX_SPEED_KMH)
        & (pl.col("next_run_h") >= HIKE_ANCHOR_MIN_H)
    )

    df = df.with_columns(
        pl.when(is_noise_gap)
        .then(pl.lit(None))
        .otherwise(pl.col("mode"))
        .forward_fill()
        .alias("mode"),
    )
    return df.drop(
        ["run_id", "run_mode", "run_h", "run_dist_km", "run_speed_kmh", "next_run_h"]
    )


def _absorb_long_gaps(df: pl.DataFrame) -> pl.DataFrame:
    """Absorb overnight camps and GPS blackouts between two hike runs.

    Camp: GPS barely moved (< 1 km), up to 20 h.
    Blackout: phone stopped logging at hike speed.  Short (< 6 h) needs
    following anchor; long (6-24 h) needs both anchors + distance cap.
    """
    df, stats = _run_stats(df)
    stats = stats.with_columns(
        pl.col("run_mode").shift(-1).alias("next_run_mode"),
        pl.col("run_mode").shift(1).alias("prev_run_mode"),
        pl.col("run_h").shift(-1).fill_null(0.0).alias("next_run_h"),
        pl.col("run_h").shift(1).fill_null(0.0).alias("prev_run_h"),
    )

    between_hikes = (
        (pl.col("run_mode") == "other")
        & (pl.col("prev_run_mode") == "hike")
        & (pl.col("next_run_mode") == "hike")
    )

    is_camp_gap = (
        between_hikes
        & (pl.col("run_dist_km") < CAMP_GAP_MAX_DIST_KM)
        & (pl.col("run_h") < CAMP_GAP_MAX_H)
        & (pl.col("prev_run_h") >= CAMP_PREV_ANCHOR_MIN_H)
    )

    # Blackout: hike speed + following anchor always required.
    # Short (< 6 h): generous distance cap.
    # Long (6-24 h): tight distance + both anchors.
    at_hike_speed = between_hikes & (pl.col("run_speed_kmh") <= HIKE_MAX_SPEED_KMH)
    is_short = pl.col("run_h") < BLACKOUT_GAP_SHORT_MAX_H
    is_blackout_gap = (
        at_hike_speed
        & (pl.col("next_run_h") >= HIKE_ANCHOR_MIN_H)
        & (
            (is_short & (pl.col("run_dist_km") < BLACKOUT_GAP_SHORT_MAX_DIST_KM))
            | (
                ~is_short
                & (pl.col("run_h") < BLACKOUT_GAP_LONG_MAX_H)
                & (pl.col("run_dist_km") < BLACKOUT_GAP_LONG_MAX_DIST_KM)
                & (pl.col("prev_run_h") >= HIKE_ANCHOR_MIN_H)
            )
        )
    )

    stats = stats.with_columns(
        pl.when(is_camp_gap | is_blackout_gap)
        .then(pl.lit("hike"))
        .otherwise(pl.col("run_mode"))
        .alias("merged_mode"),
    )
    df = df.join(stats.select("run_id", "merged_mode"), on="run_id")
    return df.with_columns(pl.col("merged_mode").alias("mode")).drop(
        ["run_id", "merged_mode"]
    )


def _absorb(df: pl.DataFrame) -> pl.DataFrame:
    """Run both absorption passes and assign segment IDs."""
    df = _absorb_noise_gaps(df)
    df = _absorb_long_gaps(df)
    return df.with_columns(pl.col("mode").rle_id().alias("segment_id"))


# ═══════════════════════════════════════════════════════════════════
#  Stage 4: Validate
# ═══════════════════════════════════════════════════════════════════


def _validate_segments(df: pl.DataFrame) -> pl.DataFrame:
    """Downgrade undersized hikes and short flights to "other"."""
    stats = df.group_by("segment_id").agg(
        pl.col("mode").first().alias("seg_mode"),
        pl.col("gap_h").sum().alias("tot_h"),
        pl.col("dist_km").sum().alias("tot_km"),
        (
            _haversine_km(
                pl.col("lat").first(),
                pl.col("lon").first(),
                pl.col("lat"),
                pl.col("lon"),
            )
        )
        .max()
        .alias("disp_km"),
    )

    ok_flight = (pl.col("seg_mode") == "flight") & (
        pl.col("tot_km") >= FLIGHT_MIN_DISTANCE_KM
    )
    ok_hike = (
        (pl.col("seg_mode") == "hike")
        & (pl.col("tot_km") >= HIKE_MIN_DISTANCE_KM)
        & (pl.col("tot_h") >= HIKE_MIN_DURATION_H)
        & (pl.col("disp_km") >= HIKE_MIN_DISPLACEMENT_KM)
    )

    stats = stats.with_columns(
        pl.when(ok_flight)
        .then(pl.lit("flight"))
        .when(ok_hike)
        .then(pl.lit("hike"))
        .otherwise(pl.lit("other"))
        .alias("final_mode"),
    )

    df = df.join(stats.select("segment_id", "final_mode"), on="segment_id")
    return df.with_columns(pl.col("final_mode").rle_id().alias("output_id"))


# ═══════════════════════════════════════════════════════════════════
#  Stage 5: Emit
# ═══════════════════════════════════════════════════════════════════


def _gdf_to_point(gdf: pl.DataFrame, idx: int) -> Point:
    return Point(lat=gdf["lat"][idx], lon=gdf["lon"][idx], time=gdf["time"][idx])


def _simplify_points(gdf: pl.DataFrame) -> list[Point]:
    """RDP-simplify a group, keeping step waypoints."""
    la, lo, ti = gdf["lat"].to_numpy(), gdf["lon"].to_numpy(), gdf["time"].to_numpy()
    mask = rdp_mask(la, lo, RDP_EPSILON_DEG)
    if "is_step" in gdf.columns:
        mask |= gdf["is_step"].to_numpy()
    return [Point(lat=la[i], lon=lo[i], time=ti[i]) for i in range(len(la)) if mask[i]]


def _resolve_kind(kind: str, gdf: pl.DataFrame) -> SegmentKind:
    """Resolve "other" → walking/driving by average speed."""
    if kind != "other":
        return SegmentKind(kind)
    total_h = float(gdf["gap_h"].sum())
    total_km = float(gdf["dist_km"].sum())
    avg = total_km / total_h if total_h > 0 else 0.0
    return SegmentKind.driving if avg > HIKE_MAX_SPEED_KMH else SegmentKind.walking


def _emit_segments(df: pl.DataFrame, steps: Sequence[Step]) -> Iterable[SegmentData]:
    """Yield SegmentData: simplify, resolve kinds, stitch consecutive segments."""
    first_step_dt = steps[0].datetime
    prev_last_pt: Point | None = None

    for _, gdf in df.group_by("output_id", maintain_order=True):
        kind = cast("str", gdf["final_mode"][0])

        if kind == "flight":
            pts = [_gdf_to_point(gdf, 0), _gdf_to_point(gdf, -1)]
            if pts[0].datetime < first_step_dt:
                continue
        else:
            pts = _simplify_points(gdf)

        # Stitch: prepend previous endpoint if there's a time gap
        if prev_last_pt is not None and (not pts or pts[0].time > prev_last_pt.time):
            pts = [prev_last_pt, *pts]

        if len(pts) < 2:
            continue

        prev_last_pt = pts[-1]
        yield SegmentData(kind=_resolve_kind(kind, gdf), points=pts)


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════


def build_segments(
    steps: Sequence[Step], locations: Iterable[Point]
) -> Iterable[SegmentData]:
    """Run the full pipeline: ingest → label → absorb → validate → emit."""
    logger.info(
        "build_segments: %d step(s), window %s → %s",
        len(steps),
        steps[0].datetime.strftime("%Y-%m-%d"),
        steps[-1].datetime.strftime("%Y-%m-%d"),
    )

    df = _ingest(steps, locations)
    logger.info("Ingested %d points after noise removal", df.height)

    if df.is_empty():
        return iter([])

    df = _label_edges(df)
    df = _absorb(df)
    df = _validate_segments(df)
    return _emit_segments(df, steps)

"""Segment a Polarsteps GPS track into typed movement segments.

The five-stage pipeline
-----------------------

  1  Ingest       Merge steps + GPS into one time-sorted stream.  Remove GPS
                  teleports and spikes.  Densify hike-speed edges to ~15 m
                  resolution so short hikes with sparse GPS are detectable.
                  Compute per-edge metrics: gap_h, dist_km, speed_kmh.

  2  Label        Classify each edge (consecutive-point pair) as "hike",
                  "flight", or "other" using speed and time-gap thresholds.
                  Edges adjacent to a step waypoint bypass the speed check —
                  the step anchors the path even when GPS was silent.

  3  Absorb       Merge short "other" interruptions back into the surrounding
                  hike in two passes:
                    a) Noise gaps: small gaps (< 4 km, < 3 h, hike speed)
                                      that are clearly GPS dropout, not transport.
                    b) Long gaps: overnight camps (GPS barely moved) and
                                      GPS blackouts in mountain terrain (hike
                                      speed confirmed); applied only on multi-day
                                      windows where overnight gaps are expected.

  4  Validate     Discard hike candidates that don't clear minimum bars: 2 h
                  elapsed, 2 km path, 1 km displacement from start.  Flights
                  shorter than 100 km are also discarded.  Rejects become "other".

  5  Emit         Convert to ``Segment`` objects.  Non-hike segments are RDP-
                  simplified for rendering efficiency.  Hike segments keep every
                  densified point: the full geometry is needed for accurate
                  elevation-based distance calculations.  "other" is resolved
                  into "walking" (≤ 6.5 km/h avg) or "driving" (faster).
                  Consecutive segments share a boundary point so the map path
                  has no gaps.

Key decisions
--------------------

Step waypoints as ground-truth anchors
    A step is where the user *was*.  We inject each step as a synthetic GPS
    point, protect it from noise-removal, and relax both the speed check and
    the gap limit for edges touching it.  Without this, an out-and-back hike
    where GPS was silent on the way to the trailhead would be split into
    several disconnected "other" segments.

``long_window`` flag
    When the requested time window spans more than 24 hours, overnight GPS
    silences are expected.  All gap thresholds and absorption windows are
    widened accordingly.  The flag is computed once in ``build_segments`` and
    threaded through as a keyword argument.

Hike segments keep all points
    Hike segments are *not* RDP-simplified.  The densified intermediate points
    carry the elevation profile needed for 3-D distance calculation.  Discarding
    even a few points can drop the turnaround of an out-and-back route, breaking
    the rendered path on the map.

Walking vs driving
    Both emerge from the pipeline as the internal label "other".  At emit time,
    the segment's average speed determines the public label: ≤ 6.5 km/h →
    ``walking`` (city strolls, GPS blackouts on foot), faster → ``driving``
    (bus, taxi, boat).

Column schema (flowing through the pipeline)
────────────────────────────────────────────
  lat, lon, time    coordinates and Unix timestamp (seconds since epoch)
  gap_h             hours elapsed since the previous point (0 for row 0)
  dist_km           haversine distance from the previous point (km)
  speed_kmh         dist_km / gap_h  (0 when gap_h == 0)
  is_step           True for rows injected from a manual step waypoint
  mode              edge label after labeling + absorption: "hike" | "flight" | "other"
  segment_id        RLE run-length ID: groups consecutive rows with the same mode
  final_mode        validated label; undersized segments downgraded to "other"
  output_id         RLE run-length ID of final_mode; one value per emitted Segment
"""

from __future__ import annotations

import heapq
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

import numpy as np
import polars as pl
from pydantic import BaseModel

from app.core.logging import config_logger

from .distance import geodist_2d, haversine_expr, haversine_expr_between
from .points import Point
from .simplify import rdp_mask

_log = config_logger(__name__)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import datetime

    from app.models.trips import Location


# ── Speed thresholds for edge classification ──────────────────────────────────
# GPS underreports speed on winding trails; a sustained hike reads ≤ 6.5 km/h
# while the actual trail pace is ~8 km/h.  Slow motorized transport (tuk-tuks,
# minibuses) typically exceeds 6.5 km/h even in traffic.
HIKE_MAX_SPEED_KMH = 6.5  # edge speed at or below this → classified on foot
FLIGHT_MIN_SPEED_KMH = 200.0  # edge speed at or above this → classified airborne

# ── Hike segment validity: all three must be satisfied ──────────────────────
# A hike that clears fewer than all three bars is downgraded to "walking".
# Displacement (start → the farthest point) filters out hostel GPS drift and
# stationary-overnight noise that accumulate path length without real movement.
HIKE_MIN_DURATION_H = 2.0  # elapsed time (hours)
HIKE_MIN_DISTANCE_KM = 2.0  # total GPS-measured path length (km)
HIKE_MIN_DISPLACEMENT_KM = 1.0  # straight-line distance from start to the farthest point (km)

# ── Flight segment validity ───────────────────────────────────────────────────
# Distinguishes a long freeway drive (which can briefly hit high speed) from
# an actual commercial flight.
FLIGHT_MIN_DISTANCE_KM = 100.0

# ── Maximum time gap for a hike edge (labeling stage) ───────────────────────
# An edge whose gap exceeds the limit is labeled "other", not "hike".
# Three variants because the acceptable silence length depends on context:
MAX_HIKE_GAP_H = 2.0  # default: short single-day window
MAX_HIKE_GAP_STEP_H = 3.5  # edge adjacent to a step waypoint: step is a reliable
# anchor even when GPS was silent for several hours
MAX_HIKE_GAP_LONG_H = 4.5  # multi-day window (> 24 h total span): overnight GPS
# gaps are common in mountain terrain

# ── GPS noise removal ─────────────────────────────────────────────────────────
# Any point with an apparent incoming speed above this is a GPS teleport and is
# dropped.  1 000 km/h is comfortably above any real-world transport including
# supersonic jets, so only impossible GPS jumps are removed.
# Step waypoints are immune: they are always kept.
TELEPORT_MAX_SPEED_KMH = 1000.0

# ── GPS densification ─────────────────────────────────────────────────────────
# Sparse GPS tracks (one point per minute) can miss short hikes entirely.
# We interpolate hike-speed edges to DENSIFY_RESOLUTION_KM point spacing so
# the labeller sees a continuous dense stream instead of a few long edges.
# Only slow edges (≤ DENSIFY_MAX_SPEED_KMH) are densified; fast edges (cabs,
# planes) stay as single long edges: they naturally become segment boundaries.
DENSIFY_MAX_SPEED_KMH = 5.0
DENSIFY_RESOLUTION_KM = 0.015  # ~15 m between interpolated points

# ── Gap absorption: pass 1: small noise gaps ─────────────────────────────────
# A short "other" run sandwiched between two hike runs is relabeled "hike"
# when it fits these caps AND moves at hike speed (looks like GPS noise, not
# real transport).  The cap on the following hike block prevents absorbing a
# gap that sits right at the END of a hike (post-hike hotel GPS drift).
NOISE_GAP_MAX_DIST_KM = 4.0  # total distance of the "other" run (km)
NOISE_GAP_MAX_H = 3.0  # total duration of the "other" run (hours)

# ── Gap absorption: pass 2: overnight camps and GPS blackouts ────────────────

# Camp gap: hiker sleeps at nearly the same spot for hours; GPS barely moves.
# Absorbed purely on distance: no speed check: because the tight distance cap
# already prevents real transport from being absorbed, and adding a speed check
# would incorrectly reject short walks-to-trailhead (e.g. 7 km/h for 30 min)
# that are semantically part of the same hiking activity.
CAMP_GAP_MAX_DIST_KM = 1.0  # GPS must stay within this radius (km)
CAMP_GAP_MAX_H = 20.0  # a full overnight absence can be up to ~20 h

# Blackout gap: phone stops logging mid-hike (mountain terrain, low battery).
# Absorbed when the gap moves at hike speed: confirming the person kept walking.
BLACKOUT_GAP_MAX_H = 6.0  # short windows (≤ 24 h span)
BLACKOUT_GAP_LONG_MAX_H = 24.0  # long windows (> 24 h span)

# Both absorption passes require a minimum hike run on each side of the gap —
# the "anchor" criterion.  Kept lower than HIKE_MIN_DURATION_H so that a
# 1.5-hour GPS fragment before a mountain camp still qualifies as an anchor.
HIKE_ANCHOR_MIN_H = 1.5

# For the camp merge specifically, the *preceding* hike run has a lower bar than
# the following one.  This guards against a brief evening city walk anchoring an
# overnight camp merge back to the previous day's hike.
CAMP_PREV_ANCHOR_MIN_H = 1.0

# ── Output ────────────────────────────────────────────────────────────────────
# Tolerance for RDP simplification of non-hike segments, in degrees.
# 0.005° ≈ 500 m at mid-latitudes: keeps major turns, drops GPS micro-wobble.
# Hike segments are NOT simplified (see module docstring).
RDP_EPSILON_DEG = 0.005


class StepLike(Protocol):
    """Structural type accepted by the pipeline.

    Matches both ``Step`` and ``PSStep`` objects.
    """

    location: Location

    @property
    def datetime(self) -> datetime: ...


class SegmentKind(StrEnum):
    flight = "flight"
    hike = "hike"
    walking = "walking"
    driving = "driving"


class Segment(BaseModel):
    kind: SegmentKind
    points: list[Point]


# ═══════════════════════════════════════════════════════════════════
#  Stage 1: Ingest
# ═══════════════════════════════════════════════════════════════════


def _points_to_df(pts: Iterable[Point]) -> pl.DataFrame:
    """Convert an iterable of Points to a column-oriented Polars DataFrame."""
    points = list(pts)
    if not points:
        return pl.DataFrame(schema={"lat": pl.Float64, "lon": pl.Float64, "time": pl.Float64})
    return pl.DataFrame(
        {
            "lat": [p.lat for p in points],
            "lon": [p.lon for p in points],
            "time": [p.time for p in points],
        }
    )


def _add_edge_metrics(df: pl.DataFrame) -> pl.DataFrame:
    """Compute per-edge gap_h, dist_km, and speed_kmh.

    Each row describes the edge *arriving at* that row from the previous one.
    Row 0 always gets gap_h=0, dist_km=0, speed_kmh=0.
    """
    return df.with_columns(
        ((pl.col("time") - pl.col("time").shift(1)) / 3600.0).fill_null(0.0).alias("gap_h"),
        (haversine_expr(lat_col="lat", lon_col="lon") / 1000.0).alias("dist_km"),
    ).with_columns(
        pl.when(pl.col("gap_h") > 0)
        .then(pl.col("dist_km") / pl.col("gap_h"))
        .otherwise(0.0)
        .alias("speed_kmh"),
    )


def _dedup_by_time(df: pl.DataFrame) -> pl.DataFrame:
    """Remove points within 1 ms of the preceding point.

    When a step waypoint is injected at a timestamp that matches an existing
    GPS point, ``heapq.merge`` places them consecutively.  The 1 ms threshold
    removes the duplicate without risking removal of legitimately close GPS
    readings (phones log no faster than ~1 Hz).
    """
    return df.filter((pl.col("time") - pl.col("time").shift(1)).abs().fill_null(1) > 0.001)


def _remove_gps_noise(df: pl.DataFrame) -> pl.DataFrame:
    """Drop GPS teleports and spikes, leaving step waypoints untouched.

    Uses degree-based distance approximation (1° ≈ 80 km) rather than
    haversine: fast enough for outlier detection, accurate enough since we
    only need to separate "impossible jumps" from "real movement".

    Two passes:
      • Teleports: points with apparent incoming speed > TELEPORT_MAX_SPEED_KMH.
      • Spikes: points that detour far from the prev→next straight line
                     (large triangle inequality violation), indicating a single
                     bad GPS fix rather than real movement.

    Step waypoints are always kept regardless of apparent speed.
    """
    has_is_step = "is_step" in df.columns
    if df.height < 2:
        return df

    # Euclidean distance in degrees / elapsed hours ≈ speed in ~80-km units
    dd = (
        (
            (pl.col("lat") - pl.col("lat").shift(1)) ** 2
            + (pl.col("lon") - pl.col("lon").shift(1)) ** 2
        )
        .sqrt()
        .fill_null(0.0)
    )
    dt = ((pl.col("time") - pl.col("time").shift(1)) / 3600.0).fill_null(1.0)
    approx_speed = dd / dt

    df = df.with_columns(approx_speed.alias("approx_speed"))

    keep = pl.col("approx_speed") <= TELEPORT_MAX_SPEED_KMH / 80.0
    if has_is_step:
        keep = keep | pl.col("is_step")
    df = df.filter(keep)

    keep_cols = ["lat", "lon", "time"] + (["is_step"] if has_is_step else [])

    if df.height < 3:
        return df.select(keep_cols)

    # Spike detection: point is far from both neighbors but prev→next is short
    dd2 = (
        (
            (pl.col("lat") - pl.col("lat").shift(1)) ** 2
            + (pl.col("lon") - pl.col("lon").shift(1)) ** 2
        )
        .sqrt()
        .fill_null(0.0)
    )
    across = (
        (pl.col("lat").shift(1) - pl.col("lat").shift(-1)) ** 2
        + (pl.col("lon").shift(1) - pl.col("lon").shift(-1)) ** 2
    ).sqrt()
    spike = ((dd2 > 0.5 / 80.0) & (across < dd2 * 0.5)).fill_null(value=False)
    if has_is_step:
        spike = spike & ~pl.col("is_step")
    df = df.filter(~spike)

    return df.select(keep_cols)


def _densify_hike_edges(df: pl.DataFrame) -> pl.DataFrame:
    """Interpolate hike-speed edges to DENSIFY_RESOLUTION_KM point spacing.

    Without densification, a hiker with GPS logging every 60 s at 5 km/h
    produces one point every ~80 m.  A two-hour hike might have only ~150
    raw points: enough for labeling, but not enough for accurate elevation-based distance.  Densification fills the gaps linearly in space and time.

    Only edges that would be labeled "hike" are densified:
      • speed   ≤ DENSIFY_MAX_SPEED_KMH   (hike pace, not a cab ride)
      • gap_h   < MAX_HIKE_GAP_H          (not a multi-hour silence)
      • dist_km > DENSIFY_RESOLUTION_KM   (already dense enough otherwise)

    The densification is fully vectorized using NumPy repeat/cumsum: no
    Python loop.  The ``is_step`` column is dropped here (the time-based
    ``is_in`` check in ``_ingest`` re-marks step rows after densification).
    """
    lats = df["lat"].to_numpy()
    lons = df["lon"].to_numpy()
    times = df["time"].to_numpy()

    if len(lats) < 2:
        return df

    dists = geodist_2d(lats, lons) / 1000.0  # km, consecutive pairs
    dts = (times[1:] - times[:-1]) / 3600.0
    speeds = np.where(dts > 0, dists / dts, 0.0)

    should_densify = (
        (speeds <= DENSIFY_MAX_SPEED_KMH) & (dists > DENSIFY_RESOLUTION_KM) & (dts < MAX_HIKE_GAP_H)
    )

    # n_pts[i] = number of output points for edge i (subdivisions if densifying, else 1 endpoint)
    n_pts = np.where(should_densify, np.ceil(dists / DENSIFY_RESOLUTION_KM).astype(int), 1)

    # Build interpolation indices without a Python loop:
    #   edge_idx[k]  = which edge output point k belongs to
    #   local_step[k] = position within that edge (0-based)
    #   frac[k]      = interpolation fraction → 1/n, 2/n, …, n/n (= endpoint)
    edge_idx = np.repeat(np.arange(len(n_pts)), n_pts)
    cum_before = np.concatenate([[0], n_pts[:-1].cumsum()])
    local_step = np.arange(n_pts.sum()) - cum_before[edge_idx]
    frac = (local_step + 1) / n_pts[edge_idx]

    i0, i1 = edge_idx, edge_idx + 1
    return pl.DataFrame(
        {
            "lat": np.concatenate([[lats[0]], lats[i0] + (lats[i1] - lats[i0]) * frac]),
            "lon": np.concatenate([[lons[0]], lons[i0] + (lons[i1] - lons[i0]) * frac]),
            "time": np.concatenate([[times[0]], times[i0] + (times[i1] - times[i0]) * frac]),
        }
    )


def _ingest(steps: Sequence[StepLike], locations: Iterable[Point]) -> pl.DataFrame:
    """Build the initial pipeline DataFrame from steps and raw GPS locations.

    Steps:
      1. Filter GPS to the day-boundary window covering the steps.
      2. Sort both streams; merge them chronologically via heapq.merge.
      3. Deduplicate on time (step + coincident GPS point → keep one).
      4. Mark step rows, then remove GPS noise (steps are immune).
      5. Densify hike-speed edges; re-mark step rows (densified rows aren't steps).
      6. Compute edge metrics (gap_h, dist_km, speed_kmh).
    """
    t0 = steps[0].datetime.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    t1 = steps[-1].datetime.replace(hour=23, minute=59, second=59, microsecond=999999).timestamp()

    # Both inputs must be sorted for heapq.merge to work correctly.
    gps = sorted(p for p in locations if t0 <= p.time <= t1)
    step_pts = sorted(
        Point(lat=s.location.lat, lon=s.location.lon, time=s.datetime.timestamp()) for s in steps
    )
    step_times = [p.time for p in step_pts]

    df = _points_to_df(heapq.merge(step_pts, gps))
    if df.height == 0:
        return df

    df = _dedup_by_time(df)
    # Mark steps BEFORE noise removal so they survive even when surrounded by
    # distant GPS points (e.g. the user was at a remote viewpoint with no signal).
    df = df.with_columns(pl.col("time").is_in(step_times).alias("is_step"))
    df = _remove_gps_noise(df)
    df = _densify_hike_edges(df)  # drops is_step column
    df = _add_edge_metrics(df)
    # Re-mark after densification: interpolated rows won't match step_times.
    return df.with_columns(pl.col("time").is_in(step_times).alias("is_step"))


# ═══════════════════════════════════════════════════════════════════
#  Stage 2: Label edges
# ═══════════════════════════════════════════════════════════════════


def _label_edges(df: pl.DataFrame, *, long_window: bool) -> pl.DataFrame:
    """Assign a transport mode label to every edge.

    Priority (highest wins):
      1. Flight: speed ≥ FLIGHT_MIN_SPEED_KMH on this edge OR the next
                   (both takeoff and landing edges are labeled flight).
      2. Hike: (speed ≤ HIKE_MAX_SPEED_KMH, OR edge is step-adjacent)
                   AND gap_h < gap_limit.
      3. Other: everything else (motorized transport, hotel drift, …).

    Step-adjacent edges (edges that start or end at a step waypoint) get two
    relaxations: the speed check is bypassed and the gap limit is wider.  This
    is correct because the step records where the user *was*, not how fast they
    got there: GPS simply didn't capture the walk.
    """
    is_flight_edge = pl.col("speed_kmh") >= FLIGHT_MIN_SPEED_KMH
    # Both the takeoff and landing edges of a flight read as flight-speed —
    # mark them together so the segment includes both endpoints.
    flight_mask = is_flight_edge | is_flight_edge.shift(-1, fill_value=False)

    step_adjacent = pl.col("is_step") | pl.col("is_step").shift(1, fill_value=False)
    gap_limit = (
        pl.when(step_adjacent)
        .then(pl.lit(MAX_HIKE_GAP_STEP_H))
        .when(pl.lit(long_window))
        .then(pl.lit(MAX_HIKE_GAP_LONG_H))
        .otherwise(pl.lit(MAX_HIKE_GAP_H))
    )
    within_gap_limit = pl.col("gap_h") < gap_limit
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
    """Compute run-level statistics for the current ``mode`` labeling.

    Returns ``(df_with_run_id, stats)`` where stats is sorted by ``run_id``
    and contains: ``run_id``, ``run_mode``, ``run_h``, ``run_dist_km``,
    ``run_speed_kmh``.  Both absorption passes call this before adding their
    own neighbor-aware columns (next_run_h, prev_run_mode, …).
    """
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
    """Pass 1: fold small GPS-noise gaps back into the surrounding hike.

    Works on run-length-encoded "mode" runs.  An "other" run is relabeled
    "hike" when it satisfies all of:
      - Distance < NOISE_GAP_MAX_DIST_KM   (didn't travel far → probably not transport)
      - Duration < NOISE_GAP_MAX_H         (short absence)
      - Avg speed ≤ HIKE_MAX_SPEED_KMH     (moved at walking pace)
      - Next hike run ≥ HIKE_ANCHOR_MIN_H  (the gap is in the *middle* of a hike,
                                             not at the end where post-hike drift accumulates)

    Relabeling is done via forward-fill: the "other" run's mode is nulled and
    filled from the preceding hike label.
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
    return df.drop(["run_id", "run_mode", "run_h", "run_dist_km", "run_speed_kmh", "next_run_h"])


def _absorb_long_gaps(df: pl.DataFrame, *, long_window: bool) -> pl.DataFrame:
    """Pass 2: absorb overnight camps and mid-hike GPS blackouts.

    Only "other" runs sandwiched between two hike runs are considered.
    Two independent merge criteria: camp and blackout: are OR-ed together.

    Camp gap (GPS stationary overnight)
        Hiker sleeps at camp; GPS barely drifts.  Absorbed when:
          - distance < CAMP_GAP_MAX_DIST_KM   (GPS stayed in one place)
          - duration < CAMP_GAP_MAX_H         (overnight absence, up to 20 h)
          - prev hike ≥ CAMP_PREV_ANCHOR_MIN_H (guard against a brief evening
                                                city walk anchoring the merge)
        No speed check: the distance cap already prevents real transport, and
        a speed check would incorrectly reject the walk to the trailhead.

    Blackout gap (GPS stopped logging mid-hike)
        Phone died / lost signal on a mountain.  Absorbed when:
          • avg speed ≤ HIKE_MAX_SPEED_KMH    (confirms on-foot movement)
          • duration < BLACKOUT_GAP_MAX_H     (6 h short / 24 h long window)
          • both surrounding hike runs ≥ HIKE_ANCHOR_MIN_H

    Thresholds widen on long windows (> 24 h) where overnight gaps are normal.
    """
    df, stats = _run_stats(df)
    stats = stats.with_columns(
        pl.col("run_mode").shift(-1).alias("next_run_mode"),
        pl.col("run_mode").shift(1).alias("prev_run_mode"),
        pl.col("run_h").shift(-1).fill_null(0.0).alias("next_run_h"),
        pl.col("run_h").shift(1).fill_null(0.0).alias("prev_run_h"),
    )

    # Effective thresholds: widened for multi-day windows
    camp_max_h = CAMP_GAP_MAX_H if long_window else NOISE_GAP_MAX_H
    camp_max_km = CAMP_GAP_MAX_DIST_KM if long_window else NOISE_GAP_MAX_DIST_KM
    blackout_max_h = BLACKOUT_GAP_LONG_MAX_H if long_window else BLACKOUT_GAP_MAX_H

    between_hikes = (
        (pl.col("run_mode") == "other")
        & (pl.col("prev_run_mode") == "hike")
        & (pl.col("next_run_mode") == "hike")
    )

    # Camp: the following hike anchor guard is only needed for short windows;
    # on long windows the distance cap (1 km) is the primary protection.
    nxt_ok_camp = pl.lit(value=True) if long_window else (pl.col("next_run_h") >= HIKE_ANCHOR_MIN_H)
    prv_ok_camp = (
        (pl.col("prev_run_h") >= CAMP_PREV_ANCHOR_MIN_H) if long_window else pl.lit(value=True)
    )
    is_camp_gap = (
        between_hikes
        & (pl.col("run_dist_km") < camp_max_km)
        & (pl.col("run_h") < camp_max_h)
        & nxt_ok_camp
        & prv_ok_camp
    )

    prv_ok_blackout = (
        (pl.col("prev_run_h") >= HIKE_ANCHOR_MIN_H) if long_window else pl.lit(value=True)
    )
    is_blackout_gap = (
        between_hikes
        & (pl.col("run_speed_kmh") <= HIKE_MAX_SPEED_KMH)
        & (pl.col("run_h") < blackout_max_h)
        & (pl.col("next_run_h") >= HIKE_ANCHOR_MIN_H)
        & prv_ok_blackout
    )

    stats = stats.with_columns(
        pl.when(is_camp_gap | is_blackout_gap)
        .then(pl.lit("hike"))
        .otherwise(pl.col("run_mode"))
        .alias("merged_mode"),
    )
    df = df.join(stats.select("run_id", "merged_mode"), on="run_id")
    return df.with_columns(pl.col("merged_mode").alias("mode")).drop(["run_id", "merged_mode"])


def _absorb(df: pl.DataFrame, *, long_window: bool) -> pl.DataFrame:
    """Run both absorption passes and assign segment IDs."""
    df = _absorb_noise_gaps(df)
    df = _absorb_long_gaps(df, long_window=long_window)
    return df.with_columns(pl.col("mode").rle_id().alias("segment_id"))


# ═══════════════════════════════════════════════════════════════════
#  Stage 4: Validate
# ═══════════════════════════════════════════════════════════════════


def _validate_segments(df: pl.DataFrame) -> pl.DataFrame:
    """Downgrade segments that don't clear minimum size thresholds.

    Hike candidates must satisfy all three bars (duration, path length,
    displacement).  Displacement: the max distance from the starting point
    reached anywhere on the segment: filters out hotel GPS drift that
    accumulates path length while the person is stationary.

    Flight candidates must cover at least FLIGHT_MIN_DISTANCE_KM to distinguish
    them from fast-moving ground transport.

    Anything that fails validation is relabeled "other" and will be resolved
    into walking or driving at emit time.
    """
    stats = df.group_by("segment_id").agg(
        pl.col("mode").first().alias("seg_mode"),
        pl.col("gap_h").sum().alias("tot_h"),
        pl.col("dist_km").sum().alias("tot_km"),
        (
            haversine_expr_between(
                pl.col("lat").first(),
                pl.col("lon").first(),
                pl.col("lat"),
                pl.col("lon"),
            )
            / 1000.0
        )
        .max()
        .alias("disp_km"),
    )

    ok_flight = (pl.col("seg_mode") == "flight") & (pl.col("tot_km") >= FLIGHT_MIN_DISTANCE_KM)
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


def _emit_segments(df: pl.DataFrame, steps: Sequence[StepLike]) -> Iterable[Segment]:
    """Convert the validated DataFrame to Segment objects.

    For each output group (output_id):
      - Flight: keep only first and last point; skip if it departs before
                  the first step (pre-trip GPS noise).
      - Hike: keep all densified points (no RDP: see module docstring).
      - Other: RDP-simplify, then resolve to walking or driving by avg speed.

    Stitching: each segment's first point is checked against the previous
    segment's last point.  If there is a time gap (RDP pruning or GPS blackout),
    the previous last point is prepended so the rendered path is fully connected.
    """
    first_step_dt = steps[0].datetime
    prev_last_pt: Point | None = None

    for _, gdf in df.group_by("output_id", maintain_order=True):
        kind: str = gdf["final_mode"][0]

        if kind == "flight":
            pts: list[Point] = [
                Point(lat=gdf["lat"][0], lon=gdf["lon"][0], time=gdf["time"][0]),
                Point(lat=gdf["lat"][-1], lon=gdf["lon"][-1], time=gdf["time"][-1]),
            ]
            if pts[0].datetime < first_step_dt:
                continue
        else:
            la = gdf["lat"].to_numpy()
            lo = gdf["lon"].to_numpy()
            ti = gdf["time"].to_numpy()

            if kind == "hike":
                pts = [Point(lat=la[i], lon=lo[i], time=ti[i]) for i in range(len(la))]
            else:
                mask = rdp_mask(la, lo, RDP_EPSILON_DEG)
                pts = [Point(lat=la[i], lon=lo[i], time=ti[i]) for i in range(len(la)) if mask[i]]

        # Prepend the previous segment's last point if there is a time gap,
        # ensuring the map polyline is visually continuous.
        if prev_last_pt is not None and (not pts or pts[0].time > prev_last_pt.time):
            pts = [prev_last_pt, *pts]

        if len(pts) < 2:
            continue

        # Resolve "other" → walking / driving based on average speed
        if kind == "other":
            total_h = float(gdf["gap_h"].sum())
            total_km = float(gdf["dist_km"].sum())
            avg_speed = total_km / total_h if total_h > 0 else 0.0
            seg_kind = (
                SegmentKind.driving if avg_speed > HIKE_MAX_SPEED_KMH else SegmentKind.walking
            )
        else:
            seg_kind = SegmentKind(kind)

        prev_last_pt = pts[-1]
        yield Segment(kind=seg_kind, points=pts)


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════


def build_segments(
    steps: Sequence[StepLike],
    locations: Iterable[Point],
) -> Iterable[Segment]:
    """Segment a Polarsteps trip into typed movement segments.

    Args:
        steps:     Ordered sequence of Polarsteps step waypoints covering the
                   desired time window.  Must contain at least one step.
        locations: Raw GPS points for the trip (need not be pre-filtered).

    Yields:
        ``Segment`` objects in chronological order, each with a ``kind``
        (hike / flight / walking / driving) and a list of ``Point`` objects.

    Raises:
        ValueError: if ``steps`` is empty.
    """
    if not steps:
        raise ValueError("build_segments requires at least one step")

    _log.debug(
        "build_segments: %d step(s), window %s → %s",
        len(steps),
        steps[0].datetime.strftime("%Y-%m-%d"),
        steps[-1].datetime.strftime("%Y-%m-%d"),
    )

    df = _ingest(steps, locations)
    _log.debug("Ingested %d points after noise removal", df.height)

    if df.is_empty():
        return iter([])

    total_span_h = (df["time"].max() - df["time"].min()) / 3600
    long_window = bool(total_span_h > 24)

    df = _label_edges(df, long_window=long_window)
    df = _absorb(df, long_window=long_window)
    df = _validate_segments(df)

    mode_counts = df.group_by("final_mode").len().sort("final_mode")
    _log.debug(
        "Segments: %s",
        dict(zip(mode_counts["final_mode"].to_list(), mode_counts["len"].to_list(), strict=False)),
    )

    return _emit_segments(df, steps)

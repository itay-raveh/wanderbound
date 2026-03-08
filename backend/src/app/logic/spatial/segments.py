"""GPS trajectory segmentation via per-edge change-point detection.

Self-contained module: haversine math, cleaning, densification, and the
segmentation pipeline itself.  Only depends on ``Point`` from ``points.py``
and ``rdp_mask`` from ``simplify.py``.

Pipeline
────────
  1. Ingest    — merge step waypoints + GPS, time-filter, clean,
                 **selectively densify** hike-speed edges
  2. Label     — classify each edge: flight / hike / other
  3. Absorb    — RLE-group, merge small noise gaps
  4. Validate  — enforce hike/flight minimums
  5. Emit      — RDP-simplify, yield ``Segment`` objects
"""

from __future__ import annotations

import heapq
import math
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

import numpy as np
import polars as pl
from pydantic import BaseModel

from .points import Point
from .simplify import rdp_mask

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import datetime

    from app.models.trips import Location


# ── Haversine ────────────────────────────────────────────────────

_R_KM = 6371.0
_TO_RAD = math.pi / 180.0


def _hav(lat1: pl.Expr, lon1: pl.Expr, lat2: pl.Expr, lon2: pl.Expr) -> pl.Expr:
    """Haversine distance (km) between two Polars coordinate-column pairs."""
    p1, p2 = lat1 * _TO_RAD, lat2 * _TO_RAD
    dp = p2 - p1
    dl = (lon2 - lon1) * _TO_RAD
    a = (dp / 2).sin() ** 2 + p1.cos() * p2.cos() * (dl / 2).sin() ** 2
    return 2 * _R_KM * pl.arctan2(a.sqrt(), (1 - a).sqrt())


def _hav_prev() -> pl.Expr:
    """Haversine (km) from each row to its predecessor."""
    return _hav(
        pl.col("lats").shift(1),
        pl.col("lons").shift(1),
        pl.col("lats"),
        pl.col("lons"),
    ).fill_null(0.0)


def _hav_np(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Numpy haversine (km) between two point arrays."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * _R_KM * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


# ── Constants ────────────────────────────────────────────────────

# Transport mode speeds
# 6.5 km/h GPS-measured ≈ 8 km/h actual on winding trail — sustained hiking
# rarely exceeds this; slow minibuses / tuk-tuks sit just above it.
MAX_HIKE_KMH = 6.5
MIN_FLIGHT_KMH = 200.0

# Minimum totals for a valid segment
MIN_FLIGHT_KM = 100.0
MIN_HIKE_KM = 2.0  # sparse GPS produces short tracks
MIN_HIKE_H = 2.0  # at least 2 h of walking (filters 1-2 h warm-up / cool-down spurts)
# 1.0 km keeps real hikes (even short loops) while rejecting GPS drift at hostels
MIN_HIKE_DISPLACEMENT_KM = 1.0

# Edge constraints
MAX_HIKE_GAP_H = 2.0  # edges longer than this are NOT hike (short windows)
# Step waypoints are manually set by the user, not raw GPS — a gap of up to 3.5 h
# adjacent to a step check-in is accepted as a continuation of an ongoing hike.
MAX_HIKE_GAP_H_STEP = 3.5
# For long multi-day windows GPS logging gaps can reach several hours.
# Allow up to 4.5 h at hike speed before labelling "other".
MAX_HIKE_GAP_H_LONG = 4.5

# Noise absorption
ABSORB_GAP_KM = 4.0
ABSORB_GAP_H = 3.0
# Overnight camp on a multi-day trek: absorb "other" between two hike segs
# even if many hours long.  Distance cap (CAMP_GAP_KM) prevents merging hikes
# that are separated by transport; only use when the window spans >24 h.
CAMP_GAP_H = 20.0
CAMP_GAP_KM = 1.0  # campsite drift is tiny; >1 km means the person moved
# Hike-speed gap merge: absorb "other" edges that are moving at hike speed between
# two hike segments — these are GPS blackouts where the phone logged nothing for
# hours but the hiker kept moving (common in mountain / jungle terrain).
# Use a short cap for single-day windows (GPS blackout during a day hike) and a
# larger cap for multi-day windows (overnight at a refugio km away from camp).
HIKE_SPEED_GAP_H = 6.0  # short-window max (single-day trips ≤ 24 h span)
HIKE_SPEED_GAP_LONG_H = 24.0  # long-window max (multi-day treks > 24 h span)
# For the hike-speed merge the following hike block must be substantial to confirm
# the gap is mid-hike (not post-hike GPS drift). Lower than MIN_HIKE_H because the
# block is a component; it doesn't need to stand alone.
MIN_HIKE_COMPONENT_H = 1.5
# For the camp-based overnight merge, require the preceding hike block to be at
# least this long so a brief town walk cannot anchor a multi-day trek to the
# previous evening.  Intentionally lower than MIN_HIKE_COMPONENT_H so that
# short mid-trek GPS blocks (e.g. 1 h before a campsite) still qualify.
MIN_CAMP_ANCHOR_H = 1.0

# Cleaning
MAX_CLEAN_KMH = 1000.0

# Densification — only edges BELOW this speed get densified
DENSIFY_MAX_KMH = 5.0  # well below typical cab speed
DENSIFY_MIN_KM = 0.015  # ~15 m resolution

# Output
RDP_EPSILON = 0.005  # degrees


class StepLike(Protocol):
    """Protocol to support both ``Step`` and `PSStep``."""

    location: Location

    @property
    def datetime(self) -> datetime: ...


# ── Public types ─────────────────────────────────────────────────


class SegmentKind(StrEnum):
    flight = "flight"
    hike = "hike"
    walking = "walking"   # slow non-hike movement (city walks, GPS blackouts)
    driving = "driving"   # motorised transport (bus, cab, boat)


class Segment(BaseModel):
    kind: SegmentKind
    points: list[Point]


# ═══════════════════════════════════════════════════════════════════
#  Stage 1 — Ingest
# ═══════════════════════════════════════════════════════════════════


def _to_df(pts: Iterable[Point]) -> pl.DataFrame:
    rows = [{"lats": p.lat, "lons": p.lon, "times": p.time} for p in pts]
    if not rows:
        return pl.DataFrame(schema={"lats": pl.Float64, "lons": pl.Float64, "times": pl.Float64})
    return pl.DataFrame(rows)


def _metrics(df: pl.DataFrame) -> pl.DataFrame:
    """Add dt_h, dd_km, speed_kmh."""
    return df.with_columns(
        ((pl.col("times") - pl.col("times").shift(1)) / 3600.0).fill_null(0.0).alias("dt_h"),
        _hav_prev().alias("dd_km"),
    ).with_columns(
        pl.when(pl.col("dt_h") > 0)
        .then(pl.col("dd_km") / pl.col("dt_h"))
        .otherwise(0.0)
        .alias("speed_kmh"),
    )


def _dedup(df: pl.DataFrame) -> pl.DataFrame:
    return df.filter((pl.col("times") - pl.col("times").shift(1)).abs().fill_null(1) > 0.001)


def _clean(df: pl.DataFrame) -> pl.DataFrame:
    """Remove GPS noise (teleports, spikes) using fast degree math.

    Step waypoints (``is_step=True``) are never removed — they are manually
    set by the user and must survive even when surrounded by distant GPS points.
    """
    has_is_step = "is_step" in df.columns
    if df.height < 2:
        return df

    # Approximate speed in degree/h (no trig, 80 km ≈ 1°)
    dd = (
        (
            (pl.col("lats") - pl.col("lats").shift(1)) ** 2
            + (pl.col("lons") - pl.col("lons").shift(1)) ** 2
        )
        .sqrt()
        .fill_null(0.0)
    )
    dt = ((pl.col("times") - pl.col("times").shift(1)) / 3600.0).fill_null(1.0)
    speed = dd / dt

    df = df.with_columns(speed.alias("_spd"))

    # Remove teleports (but never step waypoints)
    keep = pl.col("_spd") <= MAX_CLEAN_KMH / 80.0
    if has_is_step:
        keep = keep | pl.col("is_step")
    df = df.filter(keep)

    keep_cols = ["lats", "lons", "times"] + (["is_step"] if has_is_step else [])

    if df.height < 3:
        return df.select(keep_cols)

    # Remove spikes (large detour but prev→next is short)
    dd2 = (
        (
            (pl.col("lats") - pl.col("lats").shift(1)) ** 2
            + (pl.col("lons") - pl.col("lons").shift(1)) ** 2
        )
        .sqrt()
        .fill_null(0.0)
    )
    across = (
        (pl.col("lats").shift(1) - pl.col("lats").shift(-1)) ** 2
        + (pl.col("lons").shift(1) - pl.col("lons").shift(-1)) ** 2
    ).sqrt()
    spike = ((dd2 > 0.5 / 80.0) & (across < dd2 * 0.5)).fill_null(value=False)
    if has_is_step:
        spike = spike & ~pl.col("is_step")
    df = df.filter(~spike)

    return df.select(keep_cols)


def _densify_slow_edges(df: pl.DataFrame) -> pl.DataFrame:
    """Selectively densify only hike-speed edges.

    Edges faster than MAX_HIKE_KMH (cab rides, flights) stay as single
    edges — they naturally become segment boundaries.  Slow edges get
    interpolated to ~15 m resolution, filling in sparse GPS gaps so that
    short hikes with few raw points become detectable.
    """
    lats = df["lats"].to_numpy()
    lons = df["lons"].to_numpy()
    times = df["times"].to_numpy()

    if len(lats) < 2:
        return df

    # Compute per-edge distances and speeds
    dists = _hav_np(lats[:-1], lons[:-1], lats[1:], lons[1:])
    dts = (times[1:] - times[:-1]) / 3600.0
    speeds = np.where(dts > 0, dists / dts, 0.0)

    new_la, new_lo, new_t = [lats[0]], [lons[0]], [times[0]]

    for i in range(len(dists)):
        d = dists[i]
        # Only densify slow edges short enough to be labeled hike.
        # Edges with dt_h >= MAX_HIKE_GAP_H would be labeled "other" anyway;
        # densifying them would split one "other" row into many synthetic rows
        # that each pass the dt_h < MAX_HIKE_GAP_H check — creating false hike
        # evidence from long sparse gaps (e.g. GPS noise at a hotel all evening).
        if speeds[i] <= DENSIFY_MAX_KMH and d > DENSIFY_MIN_KM and dts[i] < MAX_HIKE_GAP_H:
            n = int(np.ceil(d / DENSIFY_MIN_KM))
            for j in range(1, n):
                frac = j / n
                new_la.append(lats[i] + (lats[i + 1] - lats[i]) * frac)
                new_lo.append(lons[i] + (lons[i + 1] - lons[i]) * frac)
                new_t.append(times[i] + (times[i + 1] - times[i]) * frac)
        new_la.append(lats[i + 1])
        new_lo.append(lons[i + 1])
        new_t.append(times[i + 1])

    return pl.DataFrame(
        {
            "lats": np.array(new_la),
            "lons": np.array(new_lo),
            "times": np.array(new_t),
        }
    )


def _ingest(steps: Sequence[StepLike], locations: Iterable[Point]) -> pl.DataFrame:
    """Merge, time-filter, clean, selectively densify, compute metrics."""
    t0 = steps[0].datetime.replace(hour=5, minute=0).timestamp()
    t1 = steps[-1].datetime.replace(hour=23, minute=59).timestamp()

    gps = (p for p in locations if t0 <= p.time <= t1)
    step_pts = (
        Point(lat=s.location.lat, lon=s.location.lon, time=s.datetime.timestamp()) for s in steps
    )

    step_times = [s.datetime.timestamp() for s in steps]

    df = _to_df(heapq.merge(step_pts, gps))
    if df.height == 0:
        return df

    df = _dedup(df)
    # Mark step waypoints BEFORE cleaning so _clean won't remove them as spikes.
    # Steps are manually set by the user and must survive even when surrounded
    # by GPS points that are far away.
    df = df.with_columns(pl.col("times").is_in(step_times).alias("is_step"))
    df = _clean(df)
    df = _densify_slow_edges(df)  # key: only hike-speed edges; drops is_step column
    df = _metrics(df)

    # Re-mark step waypoints after densification (densified rows won't match
    # step_times, so is_in is sufficient to identify the original step rows).
    return df.with_columns(pl.col("times").is_in(step_times).alias("is_step"))


# ═══════════════════════════════════════════════════════════════════
#  Stage 2 — Label edges
# ═══════════════════════════════════════════════════════════════════


def _label(df: pl.DataFrame) -> pl.DataFrame:
    """Classify each edge by transport mode (simple thresholds)."""
    total_span_h = (df["times"].max() - df["times"].min()) / 3600
    long_window = bool(total_span_h > 24)

    is_flight = pl.col("speed_kmh") >= MIN_FLIGHT_KMH
    flight_mask = is_flight | is_flight.shift(-1, fill_value=False)

    # Edges ending at OR starting from a step waypoint get relaxed constraints —
    # the step is a manually-placed anchor at the location the user actually visited.
    # The "speed" of the virtual edge to/from the step is not meaningful (the user
    # may have hiked there but GPS didn't record the path), so we bypass the speed
    # check for step-adjacent edges entirely (keeping only the time-gap limit and
    # the flight exclusion so a genuine flight is never silently absorbed).
    is_step_adjacent = pl.col("is_step") | pl.col("is_step").shift(1, fill_value=False)
    gap_limit = (
        pl.when(is_step_adjacent)
        .then(pl.lit(MAX_HIKE_GAP_H_STEP))
        .when(pl.lit(long_window))
        .then(pl.lit(MAX_HIKE_GAP_H_LONG))
        .otherwise(pl.lit(MAX_HIKE_GAP_H))
    )
    is_hike = (
        (pl.col("speed_kmh") <= MAX_HIKE_KMH) | (is_step_adjacent & ~flight_mask)
    ) & (pl.col("dt_h") < gap_limit)

    return df.with_columns(
        pl.when(flight_mask)
        .then(pl.lit("flight"))
        .when(is_hike)
        .then(pl.lit("hike"))
        .otherwise(pl.lit("other"))
        .alias("label"),
    )


# ═══════════════════════════════════════════════════════════════════
#  Stage 3 — Absorb noise
# ═══════════════════════════════════════════════════════════════════


def _absorb(df: pl.DataFrame) -> pl.DataFrame:
    """RLE-group labels, absorb short 'other' gaps via forward-fill."""
    df = df.with_columns(pl.col("label").rle_id().alias("_g"))

    stats = df.group_by("_g").agg(
        pl.col("label").first().alias("_l"),
        pl.col("dt_h").sum().alias("_dh"),
        pl.col("dd_km").sum().alias("_dk"),
    )
    # Sort by group id so shift gives correct neighbors.
    stats = stats.sort("_g").with_columns(
        pl.when(pl.col("_dh") > 0).then(pl.col("_dk") / pl.col("_dh")).otherwise(0.0).alias("_spd"),
        pl.col("_dh").shift(-1).fill_null(0.0).alias("_nxt_h"),
    )
    df = df.join(stats, on="_g")

    # Short 'other' gaps get absorbed into the surrounding label.
    # Speed check: don't absorb real transport (taxis, buses) — only GPS noise.
    # _nxt_h guard: don't absorb if the block AFTER the gap is tiny — that means
    # the gap is at the END of the hike, not in the middle.
    gap = (
        (pl.col("_l") == "other")
        & (pl.col("_dk") < ABSORB_GAP_KM)
        & (pl.col("_dh") < ABSORB_GAP_H)
        & (pl.col("_spd") <= MAX_HIKE_KMH)
        & (pl.col("_nxt_h") >= MIN_HIKE_COMPONENT_H)
    )

    df = df.with_columns(
        pl.when(gap).then(pl.lit(None)).otherwise(pl.col("label")).forward_fill().alias("label"),
    )
    df = df.drop(["_g", "_l", "_dh", "_dk", "_spd", "_nxt_h"])

    # Context-aware merge: upgrade 'other' sitting between two 'hike'
    df = df.with_columns(pl.col("label").rle_id().alias("_g2"))
    s2 = df.group_by("_g2").agg(
        pl.col("label").first().alias("_l2"),
        pl.col("dt_h").sum().alias("_dh2"),
        pl.col("dd_km").sum().alias("_dk2"),
    )
    # Sort by group id so shift gives correct neighbors.
    s2 = s2.sort("_g2").with_columns(
        pl.col("_l2").shift(-1).alias("_nxt"),
        pl.col("_l2").shift(1).alias("_prv"),
        pl.col("_dh2").shift(-1).fill_null(0.0).alias("_nxt_h"),
        pl.col("_dh2").shift(1).fill_null(0.0).alias("_prv_h"),
        pl.when(pl.col("_dh2") > 0)
        .then(pl.col("_dk2") / pl.col("_dh2"))
        .otherwise(0.0)
        .alias("_spd2"),
    )
    # For multi-day windows (>24 h) allow a much larger time gap so that
    # overnight camps on a trek are absorbed.  Keep the distance cap tight
    # (CAMP_GAP_KM) to prevent merging hikes separated by actual transport.
    total_span_h = (df["times"].max() - df["times"].min()) / 3600
    long_window = total_span_h > 24
    camp_gap_h = CAMP_GAP_H if long_window else ABSORB_GAP_H
    camp_gap_km = CAMP_GAP_KM if long_window else ABSORB_GAP_KM
    hike_speed_gap_h = HIKE_SPEED_GAP_LONG_H if long_window else HIKE_SPEED_GAP_H

    between_hikes = (
        (pl.col("_l2") == "other") & (pl.col("_prv") == "hike") & (pl.col("_nxt") == "hike")
    )

    # Camp-based merge: stationary overnight (GPS stays near same spot).
    # For short windows also require the next hike block to be substantial —
    # same guard as hike-speed merge to avoid extending single-day hikes with
    # post-hike GPS drift.
    nxt_ok = pl.lit(value=True) if long_window else (pl.col("_nxt_h") >= MIN_HIKE_COMPONENT_H)
    # For long windows guard against a brief town walk anchoring the overnight merge.
    prv_ok_camp = (pl.col("_prv_h") >= MIN_CAMP_ANCHOR_H) if long_window else pl.lit(value=True)
    merge_camp = (
        between_hikes
        & (pl.col("_dk2") < camp_gap_km)
        & (pl.col("_dh2") < camp_gap_h)
        & nxt_ok
        & prv_ok_camp
    )

    # Hike-speed merge: GPS blackout while actually hiking (edge moves at walking
    # speed but dt_h > MAX_HIKE_GAP_H so it was labelled "other").  The speed guard
    # ensures real motorised transport (>6.5 km/h) is never absorbed.
    # _nxt_h guard: the block AFTER the gap must be substantial — rejects post-hike drift.
    # _prv_h guard (long windows only): the block BEFORE the gap must also be
    # substantial so a short town walk on the eve of a multi-day trek cannot anchor
    # the whole trek to the previous evening.
    prv_ok = (pl.col("_prv_h") >= MIN_HIKE_COMPONENT_H) if long_window else pl.lit(value=True)
    merge_hike_speed = (
        between_hikes
        & (pl.col("_spd2") <= MAX_HIKE_KMH)
        & (pl.col("_dh2") < hike_speed_gap_h)
        & (pl.col("_nxt_h") >= MIN_HIKE_COMPONENT_H)
        & prv_ok
    )

    merge = merge_camp | merge_hike_speed
    s2 = s2.with_columns(
        pl.when(merge).then(pl.lit("hike")).otherwise(pl.col("_l2")).alias("_final"),
    )
    df = df.join(s2.select("_g2", "_final"), on="_g2")
    df = df.with_columns(pl.col("_final").alias("label")).drop(["_g2", "_final"])

    return df.with_columns(pl.col("label").rle_id().alias("seg_id"))


# ═══════════════════════════════════════════════════════════════════
#  Stage 4 — Validate
# ═══════════════════════════════════════════════════════════════════


def _validate(df: pl.DataFrame) -> pl.DataFrame:
    """Downgrade segments that don't meet minimum thresholds."""
    stats = df.group_by("seg_id").agg(
        pl.col("label").first().alias("seg_label"),
        pl.col("dt_h").sum().alias("tot_h"),
        pl.col("dd_km").sum().alias("tot_km"),
        pl.len().alias("n"),
        _hav(
            pl.col("lats").first(),
            pl.col("lons").first(),
            pl.col("lats"),
            pl.col("lons"),
        )
        .max()
        .alias("disp_km"),
    )

    ok_flight = (pl.col("seg_label") == "flight") & (pl.col("tot_km") >= MIN_FLIGHT_KM)
    ok_hike = (
        (pl.col("seg_label") == "hike")
        & (pl.col("tot_km") >= MIN_HIKE_KM)
        & (pl.col("tot_h") >= MIN_HIKE_H)
        & (pl.col("n") > 1)
        & (pl.col("disp_km") >= MIN_HIKE_DISPLACEMENT_KM)
    )

    stats = stats.with_columns(
        pl.when(ok_flight)
        .then(pl.lit("flight"))
        .when(ok_hike)
        .then(pl.lit("hike"))
        .otherwise(pl.lit("other"))
        .alias("final"),
    )

    df = df.join(stats.select("seg_id", "final"), on="seg_id")
    return df.with_columns(pl.col("final").rle_id().alias("fid"))


# ═══════════════════════════════════════════════════════════════════
#  Stage 5 — Emit
# ═══════════════════════════════════════════════════════════════════


def _emit(df: pl.DataFrame, steps: Sequence[StepLike]) -> Iterable[Segment]:
    first_step_dt = steps[0].datetime
    prev_last_pt: Point | None = None

    for _, gdf in df.group_by("fid", maintain_order=True):
        kind: str = gdf["final"][0]

        if kind == "flight":
            pts: list[Point] = [
                Point(lat=gdf["lats"][0], lon=gdf["lons"][0], time=gdf["times"][0]),
                Point(lat=gdf["lats"][-1], lon=gdf["lons"][-1], time=gdf["times"][-1]),
            ]
            if pts[0].datetime < first_step_dt:
                continue
        else:
            la = gdf["lats"].to_numpy()
            lo = gdf["lons"].to_numpy()
            ti = gdf["times"].to_numpy()

            if kind == "hike":
                # Keep all points for hike segments — intermediate points are
                # needed for accurate distance calculations (especially with
                # elevation).  Step waypoints are guaranteed to be present
                # since the pipeline injects them before densification.
                pts = [Point(lat=la[i], lon=lo[i], time=ti[i]) for i in range(len(la))]
            else:
                mask = rdp_mask(la, lo, RDP_EPSILON)
                pts = [Point(lat=la[i], lon=lo[i], time=ti[i]) for i in range(len(la)) if mask[i]]

        # Stitch to the previous emitted segment so there are no spatial gaps.
        # If this segment's first point is later than the previous segment's last
        # point (GPS blackout / RDP pruning), prepend the previous last point so
        # the visual path is fully connected.
        if prev_last_pt is not None and (not pts or pts[0].time > prev_last_pt.time):
            pts = [prev_last_pt, *pts]

        if len(pts) < 2 and kind in ("flight", "hike"):
            continue

        # Resolve the pipeline-internal "other" label into walking or driving
        # based on the segment's average speed.
        if kind == "other":
            total_h = float(gdf["dt_h"].sum())
            total_km = float(gdf["dd_km"].sum())
            avg_speed = total_km / total_h if total_h > 0 else 0.0
            seg_kind = SegmentKind.driving if avg_speed > MAX_HIKE_KMH else SegmentKind.walking
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
    """Build map segments from step waypoints and raw GPS locations.

    Yields ``Segment`` objects in chronological order.
    """
    df = _ingest(steps, locations)
    if df.is_empty():
        return []

    df = _label(df)
    df = _absorb(df)
    df = _validate(df)
    return _emit(df, steps)

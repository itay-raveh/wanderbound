"""Build movement segments from cleaned Polarsteps fixes and step pins.

Track preparation merges, filters, and densifies points. Each point carries
``incoming_*`` metrics for the edge ending there; the first point has no edge.
An indexed edge table owns those movements during output partitioning.

The stages below label points, absorb short interruptions, validate runs,
partition traces, and emit segments. Invalid hike and flight runs become
``other`` before emission resolves them to walking or driving.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from itertools import pairwise
from typing import NamedTuple, cast

import numpy as np
import polars as pl
import structlog
from simplification.cutil import simplify_coords_idx

from app.logic.spatial.segment_rules import (
    BLACKOUT_GAP_LONG_MAX_DIST_KM,
    BLACKOUT_GAP_LONG_MAX_H,
    BLACKOUT_GAP_SHORT_MAX_DIST_KM,
    BLACKOUT_GAP_SHORT_MAX_H,
    CAMP_GAP_MAX_DIST_KM,
    CAMP_GAP_MAX_H,
    CAMP_PREV_ANCHOR_MIN_H,
    FLIGHT_CONNECTION_GAP_H,
    FLIGHT_MIN_DISTANCE_KM,
    FLIGHT_MIN_SPEED_KMH,
    FLIGHT_SPARSE_MIN_DISTANCE_KM,
    FLIGHT_SPARSE_MIN_SPEED_KMH,
    HIKE_ANCHOR_MIN_H,
    HIKE_MAX_SPEED_KMH,
    HIKE_MIN_DISPLACEMENT_KM,
    HIKE_MIN_DISTANCE_KM,
    HIKE_MIN_DURATION_H,
    MAX_HIKE_GAP_H,
    NOISE_GAP_MAX_DIST_KM,
    NOISE_GAP_MAX_H,
    RDP_EPSILON_DEG,
    STEP_ADJACENT_MAX_EXTRA_KM,
)
from app.logic.spatial.track import _edge_frame, _haversine_km, _ingest, _StepLike
from app.models.polarsteps import Point
from app.models.segment import SegmentData, SegmentKind


class _Trace(NamedTuple):
    """Output points and the movement edges assigned to their trace."""

    kind: str
    points: pl.DataFrame
    edges: pl.DataFrame


logger = structlog.get_logger(__name__)

_POINT_COLUMNS = ("lat", "lon", "time", "is_step")
_INDEXED_POINT_COLUMNS = ("point_id", *_POINT_COLUMNS)
_INCOMING_EDGE_COLUMNS = (
    "incoming_gap_h",
    "incoming_dist_km",
    "incoming_speed_kmh",
)
_LABELED_COLUMNS = (*_INDEXED_POINT_COLUMNS, *_INCOMING_EDGE_COLUMNS, "mode")


def _label_edges(df: pl.DataFrame) -> pl.DataFrame:
    """Classify each edge as flight / hike / other by speed and gap.

    Flight wins over hike (both takeoff + landing edges are marked).
    Step-adjacent edges may exceed hike speed within a bounded distance.
    """
    fast_flight_edge = pl.col("incoming_speed_kmh") >= FLIGHT_MIN_SPEED_KMH
    sparse_flight_edge = (
        (pl.col("incoming_dist_km") >= FLIGHT_SPARSE_MIN_DISTANCE_KM)
        & (pl.col("incoming_speed_kmh") >= FLIGHT_SPARSE_MIN_SPEED_KMH)
        & (
            fast_flight_edge.shift(1, fill_value=False)
            | fast_flight_edge.shift(-1, fill_value=False)
        )
    )
    is_flight_edge = fast_flight_edge | sparse_flight_edge
    flight_mask = is_flight_edge | is_flight_edge.shift(-1, fill_value=False)

    step_adjacent = pl.col("is_step") | pl.col("is_step").shift(1, fill_value=False)
    within_gap_limit = pl.col("incoming_gap_h") < pl.lit(MAX_HIKE_GAP_H)
    at_hike_speed = pl.col("incoming_speed_kmh") <= HIKE_MAX_SPEED_KMH
    plausible_step_edge = pl.col("incoming_dist_km") <= (
        HIKE_MAX_SPEED_KMH * pl.col("incoming_gap_h") + STEP_ADJACENT_MAX_EXTRA_KM
    )
    is_hike_edge = (
        at_hike_speed | (step_adjacent & plausible_step_edge & ~flight_mask)
    ) & within_gap_limit

    return df.with_columns(
        pl.when(flight_mask)
        .then(pl.lit("flight"))
        .when(is_hike_edge)
        .then(pl.lit("hike"))
        .otherwise(pl.lit("other"))
        .alias("mode"),
    ).select(*_LABELED_COLUMNS)


def _run_stats(df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Group consecutive modes and describe each run and its neighbors."""
    df = df.with_columns(pl.col("mode").rle_id().alias("run_id"))
    stats = (
        df.group_by("run_id")
        .agg(
            pl.col("mode").first().alias("run_mode"),
            pl.col("incoming_gap_h").sum().alias("run_h"),
            pl.col("incoming_dist_km").sum().alias("run_dist_km"),
        )
        .sort("run_id")
        .with_columns(
            pl.when(pl.col("run_h") > 0)
            .then(pl.col("run_dist_km") / pl.col("run_h"))
            .otherwise(0.0)
            .alias("run_speed_kmh"),
        )
        .with_columns(
            pl.col("run_mode").shift(-1).alias("next_run_mode"),
            pl.col("run_mode").shift(1).alias("prev_run_mode"),
            pl.col("run_h").shift(-1).fill_null(0.0).alias("next_run_h"),
            pl.col("run_h").shift(1).fill_null(0.0).alias("prev_run_h"),
        )
    )
    return df, stats


def _absorb_noise_gaps(df: pl.DataFrame) -> pl.DataFrame:
    """Fold short GPS-dropout gaps (< 4 km, < 3 h, hike speed) back into hike.

    Requires a following hike anchor so we don't absorb post-hike drift.
    Brief transfers (< 30 min) between two hikes skip the speed check
    (e.g. taxi/shuttle between trailheads).
    Nulls the gap's mode and forward-fills from the preceding hike.
    """
    df, stats = _run_stats(df)
    df = df.join(stats, on="run_id")

    at_hike_speed = pl.col("run_speed_kmh") <= HIKE_MAX_SPEED_KMH
    is_brief_transfer = (
        (pl.col("run_h") < 0.5)
        & (pl.col("prev_run_mode") == "hike")
        & (pl.col("prev_run_h") >= HIKE_ANCHOR_MIN_H)
    )

    is_noise_gap = (
        (pl.col("run_mode") == "other")
        & (pl.col("run_dist_km") < NOISE_GAP_MAX_DIST_KM)
        & (pl.col("run_h") < NOISE_GAP_MAX_H)
        & (at_hike_speed | is_brief_transfer)
        & (pl.col("prev_run_mode") == "hike")
        & (pl.col("next_run_mode") == "hike")
        & (pl.col("next_run_h") >= HIKE_ANCHOR_MIN_H)
    )

    df = df.with_columns(
        pl.when(is_noise_gap)
        .then(pl.lit(None))
        .otherwise(pl.col("mode"))
        .forward_fill()
        .alias("mode"),
    )
    return df.drop(stats.columns)


def _absorb_long_gaps(df: pl.DataFrame) -> pl.DataFrame:
    """Absorb overnight camps and GPS blackouts between two hike runs.

    Camp: GPS barely moved (< 1 km), up to 20 h.
    Blackout: phone stopped logging at hike speed.  Short (< 6 h) needs
    following anchor; long (6-24 h) needs both anchors + distance cap.
    """
    df, stats = _run_stats(df)

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
    df = _absorb_noise_gaps(df)
    df = _absorb_long_gaps(df)
    return df.with_columns(pl.col("mode").rle_id().alias("segment_id")).select(
        *_LABELED_COLUMNS, "segment_id"
    )


def _validate_segments(df: pl.DataFrame) -> pl.DataFrame:
    """Downgrade undersized hikes, short flights, and stepless hikes to "other"."""
    stats = df.group_by("segment_id").agg(
        pl.col("mode").first().alias("seg_mode"),
        pl.col("incoming_gap_h").sum().alias("tot_h"),
        pl.col("incoming_dist_km").sum().alias("tot_km"),
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
    df = df.with_columns(pl.col("final_mode").rle_id().alias("output_id"))

    # Final pass: adjacent hikes that survived size checks are now merged into
    # one output_id.  Check has_step on these merged groups - a hike group
    # with no step anywhere in it becomes "other" (resolves to walking).
    step_check = df.group_by("output_id").agg(
        pl.col("final_mode").first().alias("out_mode"),
        pl.col("is_step").any().alias("has_step"),
    )
    stepless = step_check.filter(
        (pl.col("out_mode") == "hike") & ~pl.col("has_step")
    ).select("output_id")

    if stepless.height > 0:
        df = df.with_columns(
            pl.when(pl.col("output_id").is_in(stepless["output_id"].to_list()))
            .then(pl.lit("other"))
            .otherwise(pl.col("final_mode"))
            .alias("final_mode"),
        )
        df = df.with_columns(pl.col("final_mode").rle_id().alias("output_id"))

    return df.select(
        *_INDEXED_POINT_COLUMNS, *_INCOMING_EDGE_COLUMNS, "final_mode", "output_id"
    )


def _gdf_to_point(gdf: pl.DataFrame, idx: int) -> Point:
    return Point(lat=gdf["lat"][idx], lon=gdf["lon"][idx], time=gdf["time"][idx])


def _simplify_points(
    gdf: pl.DataFrame, *, max_time_gap_s: float | None = None
) -> list[Point]:
    """RDP-simplify a group, keeping step waypoints."""
    la, lo, ti = gdf["lat"].to_numpy(), gdf["lon"].to_numpy(), gdf["time"].to_numpy()
    keep = np.zeros(len(la), dtype=bool)
    keep[simplify_coords_idx(np.column_stack((lo, la)), RDP_EPSILON_DEG)] = True
    if "is_step" in gdf.columns:
        keep |= gdf["is_step"].to_numpy()
    if max_time_gap_s is not None:
        selected = np.flatnonzero(keep)
        for left, right in pairwise(selected):
            current = int(left)
            while ti[right] - ti[current] >= max_time_gap_s:
                next_idx = int(
                    np.searchsorted(ti, ti[current] + max_time_gap_s, side="left") - 1
                )
                current = max(current + 1, next_idx)
                keep[current] = True
    return [Point(lat=la[i], lon=lo[i], time=ti[i]) for i in range(len(la)) if keep[i]]


def _resolve_kind(kind: str, edges: pl.DataFrame) -> SegmentKind:
    if kind != "other":
        return SegmentKind(kind)
    moving = edges.filter(pl.col("gap_h") < MAX_HIKE_GAP_H)
    fast_km = float(
        moving.filter(pl.col("speed_kmh") > HIKE_MAX_SPEED_KMH)["dist_km"].sum()
    )
    slow_km = float(
        moving.filter(pl.col("speed_kmh") <= HIKE_MAX_SPEED_KMH)["dist_km"].sum()
    )
    return SegmentKind.driving if fast_km > slow_km else SegmentKind.walking


def _split_other_gaps(gdf: pl.DataFrame) -> list[pl.DataFrame]:
    return gdf.with_columns(
        (pl.col("incoming_gap_h") >= MAX_HIKE_GAP_H).cum_sum().alias("trace_id")
    ).partition_by("trace_id", maintain_order=True)


def _trace(
    kind: str, points: pl.DataFrame, edges: pl.DataFrame, *, include_first_edge: bool
) -> _Trace:
    first_point = int(points["point_id"][0])
    last_point = int(points["point_id"][-1])
    first_edge = max(1, first_point if include_first_edge else first_point + 1)
    # The edge ending at point i occupies row i - 1 in the edge table.
    return _Trace(
        kind,
        points.select(*_POINT_COLUMNS),
        edges.slice(first_edge - 1, max(0, last_point - first_edge + 1)),
    )


def _output_traces(df: pl.DataFrame, edges: pl.DataFrame) -> Iterable[_Trace]:
    """Partition runs and reject flight legs shorter than the flight minimum."""
    for _, gdf in df.group_by("output_id", maintain_order=True):
        raw_kind = cast("str", gdf["final_mode"][0])
        groups = [gdf]
        if raw_kind == "flight":
            starts = [0] + [
                i - 1
                for i, (gap, speed) in enumerate(
                    zip(
                        gdf["incoming_gap_h"].to_list(),
                        gdf["incoming_speed_kmh"].to_list(),
                        strict=True,
                    )
                )
                if i > 1
                and gap >= FLIGHT_CONNECTION_GAP_H
                and speed < FLIGHT_MIN_SPEED_KMH
            ]
            groups = [
                gdf.slice(start, end - start + 1)
                for start, end in pairwise([*starts, gdf.height - 1])
            ]
        elif raw_kind == "other":
            groups = _split_other_gaps(gdf)

        for points in groups:
            trace = _trace(
                raw_kind, points, edges, include_first_edge=raw_kind != "flight"
            )
            if (
                raw_kind == "flight"
                and trace.edges["dist_km"].sum() < FLIGHT_MIN_DISTANCE_KM
            ):
                for other_points in _split_other_gaps(points):
                    yield _trace("other", other_points, edges, include_first_edge=False)
            else:
                yield trace


def _emit_segments(traces: Iterable[_Trace]) -> Iterable[SegmentData]:
    prev_last_pt: Point | None = None

    for trace in traces:
        kind = _resolve_kind(trace.kind, trace.edges)
        if kind == SegmentKind.flight:
            pts = [_gdf_to_point(trace.points, 0), _gdf_to_point(trace.points, -1)]
        else:
            pts = _simplify_points(
                trace.points,
                max_time_gap_s=(
                    MAX_HIKE_GAP_H * 3600 if trace.kind == "other" else None
                ),
            )

        if (
            prev_last_pt is not None
            and pts
            and 0 < pts[0].time - prev_last_pt.time < MAX_HIKE_GAP_H * 3600
        ):
            pts = [prev_last_pt, *pts]

        if len(pts) < 2:
            continue

        prev_last_pt = pts[-1]
        yield SegmentData(kind=kind, points=pts)


def build_segments(
    steps: Sequence[_StepLike], locations: Iterable[Point]
) -> list[SegmentData]:
    if not steps:
        return []

    logger.info(
        "segments.build_started",
        step_count=len(steps),
        start_date=steps[0].datetime.strftime("%Y-%m-%d"),
        end_date=steps[-1].datetime.strftime("%Y-%m-%d"),
    )

    df = _ingest(steps, locations)
    logger.debug("segments.points_ingested", point_count=df.height)

    if df.is_empty():
        return []

    df = df.with_row_index("point_id")
    edges = _edge_frame(df)
    df = _label_edges(df)
    df = _absorb(df)
    df = _validate_segments(df)
    segments = list(_emit_segments(_output_traces(df, edges)))

    counts = Counter(seg.kind for seg in segments)
    logger.debug("segments.built", counts=dict(sorted(counts.items())))

    return segments

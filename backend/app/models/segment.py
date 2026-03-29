from bisect import bisect_right
from enum import StrEnum
from operator import attrgetter
from typing import Literal, NamedTuple

from pydantic import BaseModel
from sqlalchemy import ForeignKeyConstraint
from sqlmodel import Column, Field, SQLModel

from app.core.db import PydanticJSON
from app.models.polarsteps import Point


class SegmentKind(StrEnum):
    flight = "flight"
    hike = "hike"
    walking = "walking"
    driving = "driving"


class SegmentData(NamedTuple):
    """Pipeline output from GPS segmentation (not a DB model)."""

    kind: SegmentKind
    points: list[Point]


class Segment(SQLModel, table=True):
    __table_args__ = (
        ForeignKeyConstraint(
            ["uid", "aid"], ["album.uid", "album.id"], ondelete="CASCADE"
        ),
    )

    uid: int = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    aid: str = Field(primary_key=True)
    start_time: float = Field(primary_key=True)
    end_time: float = Field(primary_key=True)
    kind: SegmentKind
    timezone_id: str = Field(max_length=255)
    points: list[Point] = Field(
        sa_column=Column(PydanticJSON(list[Point]), nullable=False)
    )


class BoundaryAdjust(BaseModel):
    start_time: float
    end_time: float
    handle: Literal["start", "end"]
    new_boundary_time: float


def _interpolate_point(p0: Point, p1: Point, t: float) -> Point:
    """Linearly interpolate a GPS point at time t between p0 and p1."""
    if p1.time == p0.time:
        return Point(lat=p0.lat, lon=p0.lon, time=t)
    frac = max(0.0, min(1.0, (t - p0.time) / (p1.time - p0.time)))
    return Point(
        lat=p0.lat + frac * (p1.lat - p0.lat),
        lon=p0.lon + frac * (p1.lon - p0.lon),
        time=t,
    )


def split_segments(
    seg_a: Segment,
    seg_b: Segment,
    new_boundary_time: float,
) -> tuple[Segment, Segment]:
    """Split two adjacent segments at a new boundary time.

    Each output segment inherits its kind from the input segment that
    originally occupied that time region (earlier input -> earlier output).

    When the boundary falls between two GPS points, an interpolated point is
    created and added to both sides so each segment extends to the exact
    boundary position.

    Raises ValueError if either resulting segment would have < 2 points.
    """
    earlier_seg, later_seg = sorted([seg_a, seg_b], key=lambda s: s.points[0].time)

    if earlier_seg.points[-1].time > later_seg.points[0].time:
        raise ValueError("Segments overlap in time - cannot split overlapping segments")

    combined = [*earlier_seg.points, *later_seg.points]

    if not (combined[0].time < new_boundary_time < combined[-1].time):
        raise ValueError(
            "new_boundary_time must be strictly inside the combined segment range"
        )

    # Reject boundary times that land in a gap between non-contiguous segments
    gap_start = earlier_seg.points[-1].time
    gap_end = later_seg.points[0].time
    if gap_start < new_boundary_time < gap_end:
        raise ValueError("new_boundary_time falls in the gap between segments")

    idx = bisect_right(combined, new_boundary_time, key=attrgetter("time"))
    early_points = combined[:idx]
    late_points = combined[idx:]

    # If the boundary doesn't land exactly on a point, interpolate one
    if early_points and late_points and early_points[-1].time != new_boundary_time:
        boundary_pt = _interpolate_point(
            early_points[-1], late_points[0], new_boundary_time
        )
        early_points.append(boundary_pt)
        late_points = [boundary_pt, *late_points]

    if len(early_points) < 2 or len(late_points) < 2:
        raise ValueError("Both segments must have >= 2 points after split")

    new_earlier = Segment(
        uid=earlier_seg.uid,
        aid=earlier_seg.aid,
        start_time=early_points[0].time,
        end_time=early_points[-1].time,
        kind=earlier_seg.kind,
        timezone_id=earlier_seg.timezone_id,
        points=early_points,
    )
    new_later = Segment(
        uid=later_seg.uid,
        aid=later_seg.aid,
        start_time=late_points[0].time,
        end_time=late_points[-1].time,
        kind=later_seg.kind,
        timezone_id=later_seg.timezone_id,
        points=late_points,
    )
    return new_earlier, new_later

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, computed_field

type Lon = float
type Lat = float


class Point(BaseModel):
    lat: Lat
    lon: Lon
    time: float

    def __lt__(self, other: Point) -> bool:
        return self.time < other.time

    @computed_field(return_type=datetime)
    @property
    def datetime(self) -> AwareDatetime:
        return datetime.fromtimestamp(self.time, UTC)

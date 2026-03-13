from enum import StrEnum

UserId = int
AlbumId = str
StepIdx = int


class SegmentKind(StrEnum):
    flight = "flight"
    hike = "hike"
    walking = "walking"
    driving = "driving"

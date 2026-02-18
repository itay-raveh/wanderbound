from collections.abc import Iterator
from typing import Any, LiteralString

from geopy.point import Point

class Location:
    def __init__(self, address: str, point: Point, raw: dict[str, Any]) -> None: ...  # pyright: ignore[reportExplicitAny]
    @property
    def address(self) -> str: ...
    @property
    def latitude(self) -> float: ...
    @property
    def longitude(self) -> float: ...
    @property
    def altitude(self) -> float: ...
    @property
    def point(self) -> Point: ...
    @property
    def raw(self) -> dict[str, Any]: ...  # pyright: ignore[reportExplicitAny]

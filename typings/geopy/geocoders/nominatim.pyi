import ssl

from geopy.adapters import BaseAdapter
from geopy.geocoders.base import Geocoder
from geopy.location import Location

class Nominatim(Geocoder):
    def __init__(
        self,
        *,
        timeout: int = ...,
        user_agent: str,
        ssl_context: ssl.SSLContext = ...,
        adapter_factory: type[BaseAdapter] | None = None,
    ) -> None: ...
    async def reverse(
        self,
        query: tuple[float, float],
        *,
        zoom: int = 18,
        language: str | bool = False,
    ) -> Location | None: ...

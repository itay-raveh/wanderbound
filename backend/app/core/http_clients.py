"""App-wide httpx clients built once per lifespan.

Each external API gets a dedicated client with its own rate limit,
cache policy, and pool size. Clients are constructed inside
``lifespan_clients`` via ``AsyncExitStack`` so ``aclose`` runs in LIFO
order on shutdown. The resulting ``HttpClients`` is exposed on
``app.state.http`` and retrieved by routes via ``get_http_clients``.
"""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

import httpx
from aiolimiter import AsyncLimiter
from httpx import AsyncClient, Request

from app.core.config import get_settings
from app.core.http import http_client
from app.services.google_photos import GooglePhotosOAuth2


def _open_meteo_weight(request: Request) -> int:
    """Estimate how many API calls Open-Meteo will charge for this request.

    Elevation is charged per coordinate in the batched lat/lon params.
    Archive is charged per requested daily variable: the server multiplies each
    variable into a separate billed call, which is invisible in our HTTP count.
    """
    if request.url.path.endswith("/v1/archive"):
        daily = request.url.params.get("daily", "")
        return daily.count(",") + 1 if daily else 1
    lat = request.url.params.get("latitude", "")
    return lat.count(",") + 1 if "," in lat else 1


@dataclass(frozen=True, slots=True)
class HttpClients:
    mapbox: AsyncClient
    open_meteo: AsyncClient
    overpass: AsyncClient
    gphotos_picker: AsyncClient
    gphotos_download: AsyncClient
    gphotos_token: AsyncClient
    gphotos_oauth: GooglePhotosOAuth2


@asynccontextmanager
async def lifespan_clients() -> AsyncGenerator[HttpClients]:
    """Build all app-wide httpx clients; close them LIFO on exit."""
    settings = get_settings()
    async with AsyncExitStack() as stack:
        enter = stack.enter_async_context
        gphotos_token = await enter(http_client(cache=False))
        yield HttpClients(
            # Mapbox free tier: 300/min (matching), 60/min (directions).
            # Use the stricter shared budget.
            mapbox=await enter(http_client(limiter=AsyncLimiter(50, 60))),
            # Open-Meteo free tier: 600/min, 5000/hr. Stay under at 480/min.
            open_meteo=await enter(
                http_client(
                    limiter=AsyncLimiter(480, 60),
                    weight_fn=_open_meteo_weight,
                )
            ),
            # Overpass public endpoint: ~2 req/s fair-use policy.
            overpass=await enter(
                http_client(use_body_key=True, limiter=AsyncLimiter(2, 1))
            ),
            gphotos_picker=await enter(http_client(cache=False)),
            # Download concurrency is enforced at the HTTP pool layer.
            gphotos_download=await enter(
                http_client(
                    cache=False,
                    limits=httpx.Limits(max_connections=5),
                    follow_redirects=True,
                    timeout=300.0,
                )
            ),
            gphotos_token=gphotos_token,
            gphotos_oauth=GooglePhotosOAuth2(
                settings.VITE_GOOGLE_CLIENT_ID,
                settings.GOOGLE_CLIENT_SECRET,
                gphotos_token,
            ),
        )

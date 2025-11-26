"""Async country flag API integration using httpx."""

import base64

import httpx

from ..logger import get_logger
from ..settings import get_settings
from .async_helpers import fetch_and_cache_content_async
from .cache import get_cached, set_cached

logger = get_logger(__name__)

# Flag CDN rate limit: Conservative rate to avoid overwhelming the CDN
FLAG_API_CALLS_PER_SECOND = 2


async def get_country_flag_data_uri_async(
    client: httpx.AsyncClient, country_code: str
) -> str | None:
    """Get country flag image as data URI (async).

    Args:
        client: httpx AsyncClient instance
        country_code: ISO country code (e.g., "us", "fr")

    Returns:
        Data URI string for the flag image, or None if fetch fails
    """
    if not country_code:
        return None

    cache_key = f"flag_{country_code.lower()}"
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, str):
        return str(cached)

    try:
        settings = get_settings()
        url = settings.flag_cdn_url.format(country_code=country_code.lower())
        content = await fetch_and_cache_content_async(
            client,
            cache_key=f"flag_raw_{country_code.lower()}",
            url=url,
            timeout=5.0,
            max_attempts=3,
        )
        if content is None:
            return None

        image_data = base64.b64encode(content).decode("utf-8")
        data_uri = f"data:image/png;base64,{image_data}"
        set_cached(cache_key, data_uri)
        return data_uri
    except Exception as e:
        logger.warning(f"Failed to get flag for {country_code}: {e}")

    return None

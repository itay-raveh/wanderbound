"""Trip summary calculation service."""

from collections.abc import Sequence

from geopy.distance import distance

from src.core.logger import get_logger
from src.core.settings import settings
from src.data.context import TripOverviewTemplateCtx
from src.data.locations import LocationEntry
from src.data.models import AlbumPhoto, Step

logger = get_logger(__name__)


def calculate_trip_overview(
    steps: Sequence[Step],
    photo_data: AlbumPhoto,
    locations: list[LocationEntry],
) -> TripOverviewTemplateCtx:
    """Calculate summary statistics for the trip."""
    countries: list[tuple[str, str]] = []
    seen_countries = set[str]()

    for step in steps:
        country_code = step.location.country_code
        if country_code not in seen_countries:
            countries.append(
                (
                    step.location.country,
                    settings.flag_cdn_url.format(country_code=country_code.lower()),
                )
            )
            seen_countries.add(country_code)

    points = ((location.lat, location.lon) for location in locations)

    return TripOverviewTemplateCtx(
        countries=countries,
        total_km=f"{round(distance(*points).km):,}",
        total_days=(steps[-1].date - steps[0].date).days,
        step_count=len(steps),
        photo_count=(sum(map(len, photo_data.steps_with_photos.values()))),
    )

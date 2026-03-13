from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.models.polarsteps import PSLocations, PSTrip


async def collect_async[T](it: AsyncIterator[T]) -> list[T]:
    """Exhaust an async iterator into a list."""
    return [item async for item in it]


TEST_DATA_DIR = Path(__file__).parent / "test_data"


@pytest.fixture(scope="module")
def sa_trip_dir() -> Path:
    """Path to the South America trip test data directory."""
    trip_dir = TEST_DATA_DIR / "trip" / "south-america-2024-2025_14232450"
    assert trip_dir.exists(), f"SA test data not found at {trip_dir}"
    return trip_dir


@pytest.fixture(scope="module")
def sa_trip(sa_trip_dir: Path) -> PSTrip:
    return PSTrip.from_trip_dir(sa_trip_dir)


@pytest.fixture(scope="module")
def sa_locations(sa_trip_dir: Path) -> PSLocations:
    return PSLocations.from_trip_dir(sa_trip_dir)

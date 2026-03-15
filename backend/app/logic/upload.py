import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO

from pydantic import BaseModel
from safezip import safe_extract
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import engine
from app.models.geo import CountryCode
from app.models.polarsteps import PSTrip
from app.models.user import User

logger = logging.getLogger(__name__)


class TripMeta(BaseModel):
    id: str
    title: str
    step_count: int
    country_codes: list[CountryCode]


class UserCreated(BaseModel):
    user: User
    trips: list[TripMeta]


def _extract_user(file: BinaryIO) -> User:
    folder = Path(tempfile.mkdtemp(dir=settings.USERS_FOLDER))
    safe_extract(file, folder)
    user = User.model_validate_json((folder / "user" / "user.json").read_bytes())
    if user.folder.exists():
        shutil.rmtree(user.folder)
    folder.rename(user.folder)
    return user


async def user_from_zip(file: BinaryIO) -> UserCreated:
    user = await asyncio.to_thread(_extract_user, file)

    trips: list[TripMeta] = []
    for trip_dir in sorted(user.trips_folder.iterdir()):
        trip = PSTrip.from_trip_dir(trip_dir)
        trips.append(
            TripMeta(
                id=trip_dir.name,
                title=trip.title,
                step_count=trip.step_count,
                country_codes=list({s.location.country_code for s in trip.all_steps}),
            )
        )

    user.album_ids = [t.id for t in trips]

    async with AsyncSession(engine) as session:
        existing = await session.get(User, user.id)
        if existing:
            await session.delete(existing)
            await session.flush()
        session.add(user)
        await session.commit()
        await session.refresh(user)

    logger.info("User %d created from ZIP: %d trip(s)", user.id, len(trips))
    return UserCreated(user=user, trips=trips)

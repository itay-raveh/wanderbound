from pydantic import BaseModel

from app.models.polarsteps import CountryCode
from app.models.user import UserPublic


class TripMeta(BaseModel):
    id: str
    title: str
    step_count: int
    country_codes: list[CountryCode]


class UploadResult(BaseModel):
    user: UserPublic
    trips: list[TripMeta]

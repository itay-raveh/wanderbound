"""Google Photos domain types.

Public domain models and semantic type aliases for Google Photos media.
Transport concerns (OAuth, raw API wire shapes, tokens) live in
``app.services.google_photos``.
"""

from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import AfterValidator, BaseModel, StringConstraints

type GoogleMediaId = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9._-]+$", max_length=256)
]
type PickerSessionId = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9._-]+$", max_length=256)
]
type MimeType = str
type GoogleMediaType = Literal["TYPE_UNSPECIFIED", "PHOTO", "VIDEO"]
type VideoProcessingStatus = Literal["READY", "PROCESSING", "FAILED"]


_ALLOWED_MEDIA_HOSTS = frozenset({"lh3.googleusercontent.com"})


def _validate_media_base_url(v: str) -> str:
    host = urlparse(v).hostname
    if host not in _ALLOWED_MEDIA_HOSTS:
        msg = f"Untrusted media host: {host}"
        raise ValueError(msg)
    return v


type GoogleMediaBaseUrl = Annotated[str, AfterValidator(_validate_media_base_url)]


class GoogleMediaFile(BaseModel):
    base_url: GoogleMediaBaseUrl
    mime_type: MimeType
    filename: str
    width: int | None = None
    height: int | None = None


class PickedMediaItem(BaseModel):
    id: GoogleMediaId
    create_time: str
    type: GoogleMediaType
    media_file: GoogleMediaFile
    video_processing_status: VideoProcessingStatus | None = None


class PickerSession(BaseModel):
    id: PickerSessionId
    picker_uri: str
    polling_interval: str | None = None

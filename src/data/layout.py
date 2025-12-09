from pydantic import BaseModel


class PageLayout(BaseModel):
    """Represents a single page containing a list of photo IDs/filenames."""

    photos: list[str]


class StepLayout(BaseModel):
    """Represents the manual layout configuration for a specific step."""

    step_id: int
    name: str | None = None  # Human readable name for manual editing
    cover_photo_id: str | None = None
    pages: list[PageLayout]
    hidden_photos: list[str] = []


class AlbumLayout(BaseModel):
    """Top-level container for all manual layout overrides in the album."""

    steps: dict[int, StepLayout]  # Keyed by step_id

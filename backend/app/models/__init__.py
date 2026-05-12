# Import all SQLModel tables so SQLAlchemy registers them.
from app.models.album import Album as Album
from app.models.album_media import (
    AlbumMedia as AlbumMedia,
    AlbumMediaSourceRef as AlbumMediaSourceRef,
    AlbumMediaUndoSnapshot as AlbumMediaUndoSnapshot,
)
from app.models.segment import Segment as Segment
from app.models.step import Step as Step
from app.models.user import User as User

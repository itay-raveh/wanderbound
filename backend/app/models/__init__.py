# Import all SQLModel tables so SQLAlchemy registers them.
from app.models.album import Album as Album
from app.models.album_media import (
    AlbumMedia as AlbumMedia,
    AlbumMediaUndoSnapshot as AlbumMediaUndoSnapshot,
    StepPageMedia as StepPageMedia,
    StepUnusedMedia as StepUnusedMedia,
)
from app.models.processing import (
    ProcessingEventRow as ProcessingEventRow,
    ProcessingOperation as ProcessingOperation,
    WorkflowExecutorHeartbeat as WorkflowExecutorHeartbeat,
)
from app.models.segment import Segment as Segment
from app.models.step import Step as Step
from app.models.user import User as User

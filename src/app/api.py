from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.app.engine import AlbumService, get_album_service
from src.core.session import SESSIONS_DIR, get_session_id
from src.models.layout import StepLayout

api_router = APIRouter()


class CoverRequest(BaseModel):
    id: int
    cover: str


class VideoUpdateRequest(BaseModel):
    id: int
    src: str
    timestamp: float


class LayoutRequest(BaseModel):
    updates: list[StepLayout]


Service = Annotated[AlbumService, Depends(get_album_service, use_cache=False)]


@api_router.post("/cover")
async def handle_cover(cover_request: CoverRequest, service: Service) -> None:
    await service.update_cover(cover_request.id, cover_request.cover)


@api_router.post("/video")
async def handle_video(video_request: VideoUpdateRequest, service: Service) -> None:
    await service.update_video_timestamp(
        video_request.id, video_request.src, video_request.timestamp
    )


@api_router.post("/layout")
async def handle_layout(layout_request: LayoutRequest, service: Service) -> None:
    await service.update_layout(layout_request.updates)


@api_router.get("/session/{session_id}/assets/{file_path:path}")
async def serve_session_asset(session_id: str, file_path: str) -> FileResponse:
    """Serve files from a user's session directory securely.

    Validates:
    - Session ID matches current user's session
    - Path doesn't escape session directory (no traversal)
    - File exists
    """
    # Validate session ownership
    current_session = get_session_id()
    if session_id != current_session:
        raise HTTPException(status_code=403, detail="Access denied: wrong session")

    # Build and validate path
    session_dir = SESSIONS_DIR / session_id
    requested_path = (session_dir / file_path).resolve()

    # Prevent path traversal (ensure path is within session dir)
    try:
        requested_path.relative_to(session_dir.resolve())
    except ValueError:
        raise HTTPException(  # noqa: B904
            status_code=403, detail="Access denied: path traversal detected"
        )

    # Check file exists
    if not requested_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(requested_path)

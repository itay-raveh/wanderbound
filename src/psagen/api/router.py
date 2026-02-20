from collections.abc import Generator
from itertools import chain, repeat
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from nicegui import app
from pydantic import BaseModel

from psagen.core.logger import get_logger
from psagen.logic.album import Album
from psagen.logic.layout.builder import try_build_layout
from psagen.models.layout import StepLayout
from psagen.models.user import TripName, User

logger = get_logger(__name__)

api_router = APIRouter()


class VideoUpdateRequest(BaseModel):
    id: int
    src: str
    timestamp: float


ALBUMS: dict[TripName, Album] = {}

DependsUser = Annotated[User, Depends(User.from_storage)]


def get_current_album(user: DependsUser) -> Album:
    return ALBUMS[user.selected_trip]


DependsAlbum = Annotated[Album, Depends(get_current_album)]


@api_router.post("/video")
async def handle_video(video_request: VideoUpdateRequest, album: DependsAlbum) -> None:
    await album.update_video_timestamp(video_request.id, video_request.src, video_request.timestamp)


@api_router.post("/layout")
async def handle_layout(layout: StepLayout, album: DependsAlbum) -> None:
    logger.info("Requested update for step %d:", layout.id)

    # Try to find a good layout for each page
    layout.pages = [
        try_build_layout(page_layout.photos) or page_layout for page_layout in layout.pages
    ]

    for path, val1, val2 in _diff(
        album.config.layouts[layout.id].model_dump(), layout.model_dump()
    ):
        logger.info("%s: %s => %s", path, val1, val2)

    # Save the layout
    album.config.layouts[layout.id] = layout

    # Render
    await album.save()


@app.get("/trip/{path:path}")
async def serve_asset(path: str, user: DependsUser) -> Response:
    file = user.trips_folder / path

    # Prevent path traversal (ensure path is within session dir)
    try:
        await file.resolve(strict=True)
    except ValueError:
        raise HTTPException(  # noqa: B904
            status_code=403, detail="Access denied: path traversal detected"
        )

    # Check file exists
    if not await file.is_file():
        return Response(content="File not found", media_type="text/plain", status_code=404)

    return FileResponse(file)


class Nothing:
    def __str__(self) -> str:
        return "(nothing)"


_nothing = Nothing()


def _diff(a: Any, b: Any, path: str = "") -> Generator[tuple[str, Any, Any]]:
    if isinstance(a, dict) and isinstance(b, dict):
        for key in set(a).union(set(b)):
            yield from _diff(a.get(key, _nothing), b.get(key, _nothing), f"{path}.{key}")
    elif isinstance(a, list) and isinstance(b, list):
        for idx, (item1, item2) in enumerate(
            zip(chain(a, repeat(_nothing)), chain(b, repeat(_nothing)), strict=True)
        ):
            if item1 is _nothing and item2 is _nothing:
                break
            yield from _diff(item1, item2, f"{path}[{idx}]")
    elif a != b:
        yield path, a, b

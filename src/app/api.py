from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from src.app.engine import generate_step_layouts
from src.app.state import state
from src.layout.builder import try_build_layout
from src.models.layout import AlbumLayout, StepLayout, Video
from src.services.media import extract_frame, frame_path, load_photo

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import Request

api_router = APIRouter()


class CoverRequest(BaseModel):
    id: int
    cover: Path


class VideoUpdateRequest(BaseModel):
    id: int
    src: Path
    timestamp: float


class LayoutRequest(BaseModel):
    updates: list[StepLayout]


@api_router.post("/cover")
async def handle_cover(cover_request: CoverRequest) -> Response:
    layout = AlbumLayout.model_validate_json(state.layout_file.read_text())

    # Replace cover
    step_layout = layout.steps[cover_request.id]
    old_cover = step_layout.cover
    step_layout.cover = cover_request.cover

    # if the old cover was not in any of the pages
    if not any(old_cover in [photo.path for photo in page.photos] for page in step_layout.pages):
        # then we need to find the page with the new cover,
        # and replace it with the old cover
        for page in step_layout.pages:
            for idx, photo in enumerate(page.photos):
                if photo.path == cover_request.cover:
                    page.photos[idx] = await load_photo(old_cover)
                    break

    state.layout_file.write_text(layout.model_dump_json(indent=2))

    await generate_step_layouts([cover_request.id])
    return JSONResponse({"success": True})


@api_router.post("/video")
async def handle_video(video_request: VideoUpdateRequest) -> Response:
    layout = AlbumLayout.model_validate_json(state.layout_file.read_text())

    for page in layout.steps[video_request.id].pages:
        for photo in page.photos:
            if isinstance(photo, Video) and photo.src == video_request.src:
                photo.path = frame_path(
                    video_request.src, video_request.timestamp, state.args.output
                )
                photo.timestamp = video_request.timestamp
                await extract_frame(photo.src, photo.timestamp, photo.path)
                break

    state.layout_file.write_text(layout.model_dump_json(indent=2))
    await generate_step_layouts([video_request.id])
    return JSONResponse({"success": True})


@api_router.post("/layout")
async def handle_layout(layout_request: LayoutRequest) -> Response:
    layout = AlbumLayout.model_validate_json(state.layout_file.read_text())

    for step_layout in layout_request.updates:
        step_layout.pages = [
            try_build_layout(page_layout.photos) or page_layout for page_layout in step_layout.pages
        ]
        layout.steps[step_layout.id] = step_layout

    state.layout_file.write_text(layout.model_dump_json(indent=2))
    await generate_step_layouts([step_layout.id for step_layout in layout_request.updates])
    return JSONResponse({"success": True})

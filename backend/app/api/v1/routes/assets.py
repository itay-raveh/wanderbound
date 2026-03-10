from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.logic.layout.media import extract_frame

from ..deps import UserDep

# The prefix is `/trip` because that is the Polarsteps folder structure
router = APIRouter(prefix="/trip", tags=["assets"])


@router.get("/{asset_rel_path:path}")
async def get_trip_asset(asset_rel_path: Path, user: UserDep) -> FileResponse:
    normalized = (user.trips_folder / asset_rel_path).resolve()

    if (
        normalized.suffix.lower() not in {".jpg", ".jpeg", ".png", ".mp4"}
        or not normalized.is_relative_to(user.trips_folder)
        or not normalized.is_file(follow_symlinks=False)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    return FileResponse(normalized)


@router.patch("/{video:path}")
async def update_video_frame(video: Path, timestamp: int) -> None:
    await extract_frame(video, timestamp)

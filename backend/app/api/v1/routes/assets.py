from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.logic.layout.media import extract_frame
from app.models.db import User

from ..deps import UserDep

# The prefix is `/trip` because that is the Polarsteps folder structure
router = APIRouter(prefix="/trip", tags=["assets"])

MEDIA_EXTS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".mp4"})


def _resolve_asset(
    user: User, rel_path: Path, allowed: frozenset[str] = MEDIA_EXTS
) -> Path:
    resolved = (user.trips_folder / rel_path).resolve()
    if (
        resolved.suffix.lower() not in allowed
        or not resolved.is_relative_to(user.trips_folder)
        or not resolved.is_file(follow_symlinks=False)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return resolved


@router.get("/{asset_rel_path:path}")
async def get_trip_asset(asset_rel_path: Path, user: UserDep) -> FileResponse:
    return FileResponse(_resolve_asset(user, asset_rel_path))


@router.patch("/{video:path}")
async def update_video_frame(video: Path, timestamp: float, user: UserDep) -> None:
    await extract_frame(_resolve_asset(user, video, frozenset({".mp4"})), timestamp)

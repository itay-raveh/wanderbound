from fastapi import APIRouter

from .routes import (
    albums,
    assets,
    auth,
    config,
    external_media,
    google_photos,
    health,
    panoramas,
    photo_edits,
    uploads,
    users,
)

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(uploads.router)
router.include_router(albums.router)
router.include_router(external_media.router)
router.include_router(assets.router)
router.include_router(panoramas.router)
router.include_router(photo_edits.router)
router.include_router(google_photos.router)
router.include_router(config.router)

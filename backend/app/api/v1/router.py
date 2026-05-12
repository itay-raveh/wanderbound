from fastapi import APIRouter

from .routes import (
    albums,
    assets,
    auth,
    external_media,
    google_photos,
    health,
    media_imports,
    users,
)

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(albums.router)
router.include_router(external_media.router)
router.include_router(media_imports.router)
router.include_router(assets.router)
router.include_router(google_photos.router)

from fastapi import APIRouter

from .routes import albums, assets, users

router = APIRouter()
router.include_router(users.router)
router.include_router(albums.router)
router.include_router(assets.router)


@router.get("/health", tags=["health"])
async def health_check() -> bool:
    return True

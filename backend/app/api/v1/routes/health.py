import shutil

import structlog
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.resources import MiB

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["health"])

_MIN_DISK_FREE_MB = 256


class HealthStatus(BaseModel):
    db: bool
    disk: bool
    playwright: bool


@router.get("/health", response_model=HealthStatus)
async def health_check(request: Request) -> JSONResponse:
    db_ok = await _check_db()
    disk_ok, disk_free_mb = _check_disk()
    pw_ok = _check_playwright(request)

    healthy = db_ok and disk_ok and pw_ok
    if not healthy:
        logger.warning(
            "health.degraded",
            db=db_ok,
            disk=disk_ok,
            disk_free_mb=disk_free_mb,
            playwright=pw_ok,
        )

    body = HealthStatus(db=db_ok, disk=disk_ok, playwright=pw_ok)
    code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(body.model_dump(), status_code=code)


async def _check_db() -> bool:
    try:
        async with AsyncSession(get_engine()) as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("health.db_failed")
        return False
    else:
        return True


def _check_disk() -> tuple[bool, int]:
    data_folder = get_settings().DATA_FOLDER
    usage = shutil.disk_usage(data_folder)
    free_mb = usage.free // MiB
    return free_mb >= _MIN_DISK_FREE_MB, free_mb


def _check_playwright(request: Request) -> bool:
    manager = getattr(request.app.state, "browser_manager", None)
    return manager is not None and manager.connected

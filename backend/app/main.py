import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import NoResultFound
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import settings

if TYPE_CHECKING:
    from fastapi.routing import APIRoute

logger = logging.getLogger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    return route.name


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings.USERS_FOLDER.mkdir(parents=True, exist_ok=True)

    from playwright.async_api import async_playwright  # noqa: PLC0415

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(args=["--use-gl=angle"])
    app.state.browser = browser
    logger.info("Playwright browser launched")
    yield
    await browser.close()
    await pw.stop()
    logger.info("Playwright browser closed")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,  # type: ignore[invalid-argument-type]
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(
    SessionMiddleware,  # ty: ignore[invalid-argument-type]
    secret_key=settings.SECRET_KEY,
    session_cookie="session",
    max_age=30 * 86400,  # 30 days
    same_site="lax",
    https_only=settings.ENVIRONMENT != "local",
)

# GZip responses >= 500 bytes (added after CORS so it wraps the response last).
app.add_middleware(GZipMiddleware, minimum_size=500)  # type: ignore[arg-type]

app.include_router(v1_router, prefix=settings.API_V1_STR)


@app.exception_handler(NoResultFound)
async def _not_found(_request: Request, _exc: NoResultFound) -> PlainTextResponse:
    return PlainTextResponse("Not Found", status.HTTP_404_NOT_FOUND)

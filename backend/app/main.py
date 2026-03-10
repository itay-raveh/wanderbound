import http
import time
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.deps import USER_COOKIE
from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.logging import config_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi.routing import APIRoute

logger = config_logger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    return route.name


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,  # type: ignore[invalid-argument-type]
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(v1_router, prefix=settings.API_V1_STR)


@app.middleware("http")
async def access_log(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start_time = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    logger.info(
        "[%s][%s:%-5s] %-5s %s [%s] %s %s [/] (%d ms)",
        request.cookies.get(USER_COOKIE, "unknown"),
        request.client.host if request.client else "unknown",
        request.client.port if request.client else "unknown",
        request.method,
        request.url.path,
        "on red" if response.status_code >= 400 else "on green",
        response.status_code,
        http.HTTPStatus(response.status_code).phrase,
        elapsed_ms,
    )

    return response

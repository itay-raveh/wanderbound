from typing import TYPE_CHECKING

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class EarlyDataMiddleware:
    def __init__(self, app: ASGIApp, *, api_prefix: str) -> None:
        self.app = app
        self.api_prefix = api_prefix.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and (
                scope["path"] == self.api_prefix
                or scope["path"].startswith(f"{self.api_prefix}/")
            )
            # Invalid or repeated values also signal early data.
            # https://www.rfc-editor.org/rfc/rfc8470.html#section-5.1
            and "early-data" in Headers(scope=scope)
        ):
            response = JSONResponse(
                {"detail": "Too Early"},
                status_code=425,
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

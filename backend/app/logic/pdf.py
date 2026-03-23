import asyncio
import base64
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated, Literal

from playwright.async_api import Browser, Page, async_playwright
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.resources import MiB, detect_memory_mb
from app.core.tokens import TokenStore

logger = logging.getLogger(__name__)

_PDF_BASELINE_MB = 512
_PER_RENDER_MB = 768

_memory_mb = detect_memory_mb()
_max_concurrent = max(1, (_memory_mb - _PDF_BASELINE_MB) // _PER_RENDER_MB)

_render_sem = asyncio.Semaphore(_max_concurrent)

_QUEUE_TIMEOUT = 120
_RENDER_TIMEOUT = 300
_PROGRESS_CHUNK_BYTES = 512 * 1024


class PdfQueued(BaseModel):
    type: Literal["queued"] = "queued"


class PdfProgress(BaseModel):
    type: Literal["progress"] = "progress"
    phase: Literal["loading", "rendering"]
    done: int


class PdfDone(BaseModel):
    type: Literal["done"] = "done"
    token: str


class PdfError(BaseModel):
    type: Literal["error"] = "error"
    detail: str


PdfEvent = Annotated[
    PdfQueued | PdfProgress | PdfDone | PdfError,
    Field(discriminator="type"),
]

_tokens: TokenStore[tuple[Path, str]] = TokenStore(
    dir_name="wanderbound-pdf",
    ttl=60,
    label="PDF",
    on_evict=lambda d: d[0].unlink(missing_ok=True),
)


@asynccontextmanager
async def lifespan() -> AsyncGenerator[Browser]:
    """Setup/teardown for PDF rendering: tmp dir cleanup + Playwright browser."""
    async with _tokens.lifespan():
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(args=["--use-gl=angle", "--no-sandbox"])
        logger.info("Playwright browser launched")
        try:
            yield browser
        finally:
            await browser.close()
            await pw.stop()
            logger.info("Playwright browser closed")


def store_pdf_token(path: Path, aid: str) -> str:
    return _tokens.store((path, aid))


pop_pdf_token = _tokens.pop


async def _stream_pdf_to_file(page: Page, dest: Path) -> AsyncGenerator[int]:
    """Stream PDF to disk via CDP, yielding cumulative bytes written.

    Bypasses Playwright's base64 serialization and V8 string size limit.
    """
    cdp = await page.context.new_cdp_session(page)
    handle: str | None = None
    try:
        result = await cdp.send(
            "Page.printToPDF",
            {
                "preferCSSPageSize": True,
                "printBackground": True,
                "marginTop": 0,
                "marginRight": 0,
                "marginBottom": 0,
                "marginLeft": 0,
                "transferMode": "ReturnAsStream",
            },
        )
        handle = result["stream"]

        size = 0
        with dest.open("wb") as f:
            while True:
                chunk = await cdp.send("IO.read", {"handle": handle, "size": MiB})
                raw = base64.b64decode(chunk["data"])
                f.write(raw)
                size += len(raw)
                yield size
                if chunk.get("eof", False):
                    break
    finally:
        if handle is not None:
            with suppress(Exception):
                await cdp.send("IO.close", {"handle": handle})
        with suppress(Exception):
            await cdp.detach()


async def _render_pdf(
    browser: Browser,
    aid: str,
    dest: Path,
    *,
    session_cookie: str,
    dark: bool,
) -> AsyncGenerator[PdfProgress]:
    settings = get_settings()
    yield PdfProgress(phase="loading", done=0)

    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        device_scale_factor=2,
    )
    try:
        await context.add_cookies(
            [
                {
                    "name": "session",
                    "value": session_cookie,
                    "url": settings.VITE_FRONTEND_URL,
                },
            ]
        )
        page = await context.new_page()
        page.on("console", lambda msg: logger.debug("Browser: %s", msg.text))
        page.on(
            "pageerror",
            lambda err: logger.warning("Browser page error during PDF render: %s", err),
        )
        await page.emulate_media(media="print")
        dark_param = "true" if dark else "false"
        url = f"{settings.VITE_FRONTEND_URL}/print/{aid}?dark={dark_param}"
        await page.goto(url, wait_until="domcontentloaded")
        logger.info("DOM loaded for album %s", aid)
        await page.wait_for_function("window.__PRINT_READY__ === true", timeout=60_000)
        yield PdfProgress(phase="loading", done=1)

        yield PdfProgress(phase="rendering", done=0)
        size = 0
        last_reported = 0
        async with aclosing(_stream_pdf_to_file(page, dest)) as stream:
            async for size in stream:
                if size - last_reported >= _PROGRESS_CHUNK_BYTES:
                    yield PdfProgress(phase="rendering", done=size)
                    last_reported = size
        yield PdfProgress(phase="rendering", done=size)
        logger.info("PDF generated for album %s: %d bytes", aid, size)

    finally:
        await context.close()


async def render_album_pdf_stream(
    browser: Browser,
    aid: str,
    *,
    session_cookie: str,
    dark: bool = True,
) -> AsyncIterator[PdfEvent]:
    """Top-level SSE generator: queued -> loading -> rendering -> done/error."""
    yield PdfQueued()

    try:
        async with asyncio.timeout(_QUEUE_TIMEOUT):
            await _render_sem.acquire()
    except TimeoutError:
        logger.warning("PDF queue timeout for album %s after %ds", aid, _QUEUE_TIMEOUT)
        yield PdfError(
            detail="Timed out waiting for a PDF render slot. Please try again."
        )
        return

    dest = _tokens.make_dest(".pdf")
    size = 0
    owned = False
    try:
        async with asyncio.timeout(_RENDER_TIMEOUT):
            async with aclosing(
                _render_pdf(
                    browser,
                    aid,
                    dest,
                    session_cookie=session_cookie,
                    dark=dark,
                )
            ) as events:
                async for event in events:
                    if isinstance(event, PdfProgress) and event.phase == "rendering":
                        size = event.done
                    yield event

        if size == 0:
            yield PdfError(detail="PDF generation produced no output.")
            return
        token = store_pdf_token(dest, aid)
        owned = True
        yield PdfDone(token=token)

    except TimeoutError:
        logger.warning(
            "PDF render timeout for album %s after %ds", aid, _RENDER_TIMEOUT
        )
        yield PdfError(detail="PDF rendering timed out. Please try again.")
    except Exception:
        logger.exception("PDF generation failed for album %s", aid)
        yield PdfError(detail="PDF generation failed. Please try again.")
    finally:
        if not owned:
            dest.unlink(missing_ok=True)
        _render_sem.release()

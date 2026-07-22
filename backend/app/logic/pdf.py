from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import (
    AbstractAsyncContextManager,
    aclosing,
    asynccontextmanager,
    suppress,
)
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal
from urllib.parse import quote, urlencode

import structlog
from playwright.async_api import Browser, Page, Playwright, async_playwright
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.locks import try_advisory_lock
from app.core.observability import set_span_data, start_span
from app.core.resources import MiB, detect_memory_mb
from app.core.tokens import ArtifactTokenStore

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.get_logger(__name__)

_PDF_BASELINE_MB = 512
_PER_RENDER_MB = 768

_memory_mb = detect_memory_mb()
_max_concurrent = max(1, (_memory_mb - _PDF_BASELINE_MB) // _PER_RENDER_MB)

PDF_QUEUE_TIMEOUT = 120
_RENDER_TIMEOUT = 300
_PROGRESS_CHUNK_BYTES = 512 * 1024
_RENDER_SLOT_POLL_INTERVAL = 0.25


class PdfQueued(BaseModel):
    type: Literal["queued"] = "queued"


class PdfProgress(BaseModel):
    type: Literal["progress"] = "progress"
    phase: Literal["loading", "rendering"]
    done: int
    total: int | None = None


class PdfDone(BaseModel):
    type: Literal["done"] = "done"
    token: str


class PdfError(BaseModel):
    type: Literal["error"] = "error"
    detail: str


class PdfArtifact(BaseModel):
    path: Path
    filename: str
    media_type: str


class PdfQueueTimeoutError(TimeoutError):
    pass


PdfEvent = Annotated[
    PdfQueued | PdfProgress | PdfDone | PdfError,
    Field(discriminator="type"),
]


class _PdfTokens:
    def __init__(self) -> None:
        self._store = ArtifactTokenStore(
            dir_name="wanderbound-pdf",
            ttl=60,
            label="PDF",
            on_evict=lambda data: Path(data["path"]).unlink(missing_ok=True),
        )

    def cleanup(self) -> None:
        self._store.cleanup()

    def make_dest(self, suffix: str) -> Path:
        return self._store.make_dest(suffix)

    async def store(self, session: AsyncSession, artifact: PdfArtifact) -> str:
        return await self._store.store(
            session,
            {
                "path": str(artifact.path),
                "filename": artifact.filename,
                "media_type": artifact.media_type,
            },
        )

    async def pop(self, session: AsyncSession, token: str) -> PdfArtifact | None:
        data = await self._store.pop(session, token)
        if data is None:
            return None
        return PdfArtifact(
            path=Path(data["path"]),
            filename=data["filename"],
            media_type=data["media_type"],
        )

    def lifespan(self) -> AbstractAsyncContextManager[None]:
        return self._store.lifespan()


pdf_tokens = _PdfTokens()


class BrowserManager:
    """Lazy-reconnecting wrapper around a Playwright Chromium browser.

    If Chromium crashes (OOM, segfault), the next call to `get()` relaunches it.
    An asyncio.Lock ensures only one coroutine launches at a time.
    """

    _LAUNCH_ARGS: ClassVar[list[str]] = ["--use-gl=angle", "--no-sandbox"]

    def __init__(self, pw: Playwright) -> None:
        self._pw = pw
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def launch(self) -> None:
        self._browser = await self._pw.chromium.launch(args=self._LAUNCH_ARGS)
        logger.info("playwright.browser_launched")

    async def get(self) -> Browser:
        if self._browser is not None and self._browser.is_connected():
            return self._browser
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                logger.warning("playwright.browser_disconnected")
                self._browser = await self._pw.chromium.launch(args=self._LAUNCH_ARGS)
                logger.info("playwright.browser_relaunched")
        return self._browser

    @property
    def connected(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()


@asynccontextmanager
async def lifespan() -> AsyncGenerator[BrowserManager]:
    """Setup/teardown for PDF rendering: tmp dir cleanup + Playwright browser."""
    async with pdf_tokens.lifespan():
        pw = await async_playwright().start()
        manager = BrowserManager(pw)
        await manager.launch()
        try:
            yield manager
        finally:
            await manager.close()
            await pw.stop()
            logger.info("playwright.browser_closed")


async def store_pdf_token(session: AsyncSession, path: Path, aid: str) -> str:
    return await pdf_tokens.store(
        session,
        PdfArtifact(
            path=path,
            filename=f"{aid}.pdf",
            media_type="application/pdf",
        ),
    )


async def store_pdf_artifact(session: AsyncSession, artifact: PdfArtifact) -> str:
    return await pdf_tokens.store(session, artifact)


pop_pdf_token = pdf_tokens.pop


@asynccontextmanager
async def render_pdf_slot() -> AsyncGenerator[None]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PDF_QUEUE_TIMEOUT
    while True:
        for slot in range(_max_concurrent):
            lock = try_advisory_lock(f"pdf-render:{slot}")
            acquired = await lock.__aenter__()
            if acquired:
                try:
                    yield
                finally:
                    await lock.__aexit__(None, None, None)
                return
            await lock.__aexit__(None, None, None)

        if loop.time() >= deadline:
            raise TimeoutError
        await asyncio.sleep(_RENDER_SLOT_POLL_INTERVAL)


async def acquire_pdf_render_slot(
    aid: str,
    span_name: str,
) -> AbstractAsyncContextManager[None]:
    try:
        with start_span(
            span_name,
            "Wait for PDF render slot",
            **{"app.workflow": "pdf", "album.id": aid},
        ):
            slot = render_pdf_slot()
            await slot.__aenter__()
            return slot
    except TimeoutError as e:
        logger.warning(
            "pdf.queue_timeout",
            album_id=aid,
            timeout_s=PDF_QUEUE_TIMEOUT,
        )
        raise PdfQueueTimeoutError from e


def pdf_queue_timeout_event() -> PdfError:
    return PdfError(detail="Timed out waiting for a PDF render slot. Please try again.")


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


def _print_url(
    frontend_url: str,
    aid: str,
    *,
    dark: bool,
    chapter: str | None,
) -> str:
    query = {"dark": "true" if dark else "false"}
    if chapter is not None:
        query["chapter"] = chapter
    return f"{frontend_url.rstrip('/')}/print/{quote(aid)}?{urlencode(query)}"


async def render_pdf_file(  # noqa: C901, PLR0913, PLR0915
    browser: Browser,
    aid: str,
    dest: Path,
    *,
    session_cookie: str,
    dark: bool,
    chapter: str | None = None,
) -> AsyncGenerator[PdfProgress]:
    settings = get_settings()
    frontend_url = str(settings.INTERNAL_URL).rstrip("/")
    yield PdfProgress(phase="loading", done=0)

    with start_span(
        "pdf.browser_context",
        "Create PDF browser context",
        **{"app.workflow": "pdf", "album.id": aid, "pdf.dark": dark},
    ):
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,
            bypass_csp=True,
        )
    try:
        await context.add_cookies(
            [
                {
                    "name": "session",
                    "value": session_cookie,
                    "url": frontend_url,
                },
            ]
        )
        page = await context.new_page()
        page.on("console", lambda msg: logger.debug("browser.console", text=msg.text))
        page.on(
            "pageerror",
            lambda err: logger.warning(
                "pdf.browser_page_error",
                error_type=type(err).__name__,
            ),
        )
        started, finished = 0, 0

        def _on_request(_: object) -> None:
            nonlocal started
            started += 1

        def _on_finished(_: object) -> None:
            nonlocal finished
            finished += 1

        page.on("request", _on_request)
        page.on("requestfinished", _on_finished)
        page.on("requestfailed", _on_finished)
        await page.emulate_media(media="print")
        url = _print_url(frontend_url, aid, dark=dark, chapter=chapter)
        with start_span(
            "pdf.load_page",
            "Load print page",
            **{"app.workflow": "pdf", "album.id": aid, "pdf.dark": dark},
        ) as span:
            await page.goto(url, wait_until="domcontentloaded")
            logger.info("pdf.dom_loaded", album_id=aid)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 60
            last_counts = (-1, -1)
            while True:
                ready = await page.evaluate("window.__PRINT_READY__ === true")
                counts = (finished, started)
                if counts != last_counts or ready:
                    last_counts = counts
                    yield PdfProgress(
                        phase="loading",
                        done=finished,
                        total=started,
                    )
                if ready:
                    break
                if loop.time() > deadline:
                    raise TimeoutError("Timed out waiting for album to load")
                await asyncio.sleep(0.5)
            set_span_data(
                span,
                **{
                    "browser.request.started": started,
                    "browser.request.finished": finished,
                },
            )

        yield PdfProgress(phase="rendering", done=0)
        size = 0
        last_reported = 0
        with start_span(
            "pdf.print",
            "Print PDF",
            **{"app.workflow": "pdf", "album.id": aid, "pdf.dark": dark},
        ) as span:
            async with aclosing(_stream_pdf_to_file(page, dest)) as stream:
                async for size in stream:
                    if size - last_reported >= _PROGRESS_CHUNK_BYTES:
                        yield PdfProgress(phase="rendering", done=size)
                        last_reported = size
            set_span_data(span, **{"pdf.size_bytes": size})
        yield PdfProgress(phase="rendering", done=size)
        logger.info("pdf.generated", album_id=aid, size_bytes=size)

    finally:
        await context.close()


async def render_album_pdf_stream(  # noqa: PLR0913
    browser: Browser,
    session: AsyncSession,
    aid: str,
    *,
    session_cookie: str,
    dark: bool = True,
    chapter: str | None = None,
) -> AsyncIterator[PdfEvent]:
    """Top-level SSE generator: queued -> loading -> rendering -> done/error."""
    logger.info("pdf.render_queued", album_id=aid)
    yield PdfQueued()

    try:
        slot = await acquire_pdf_render_slot(aid, "pdf.queue_wait")
    except PdfQueueTimeoutError:
        yield pdf_queue_timeout_event()
        return

    dest = pdf_tokens.make_dest(".pdf")
    size = 0
    owned = False
    try:
        with start_span(
            "pdf.render",
            "Render album PDF",
            **{"app.workflow": "pdf", "album.id": aid, "pdf.dark": dark},
        ) as span:
            async with asyncio.timeout(_RENDER_TIMEOUT):
                async with aclosing(
                    render_pdf_file(
                        browser,
                        aid,
                        dest,
                        session_cookie=session_cookie,
                        dark=dark,
                        chapter=chapter,
                    )
                ) as events:
                    async for event in events:
                        if (
                            isinstance(event, PdfProgress)
                            and event.phase == "rendering"
                        ):
                            size = event.done
                        yield event
            set_span_data(span, **{"pdf.size_bytes": size})

        if size == 0:
            yield PdfError(detail="PDF generation produced no output.")
            return
        token = await store_pdf_token(session, dest, aid)
        owned = True
        yield PdfDone(token=token)

    except TimeoutError:
        logger.warning(
            "pdf.render_timeout",
            album_id=aid,
            timeout_s=_RENDER_TIMEOUT,
        )
        yield PdfError(detail="PDF rendering timed out. Please try again.")
    except Exception:
        logger.exception("pdf.generation_failed", album_id=aid)
        yield PdfError(detail="PDF generation failed. Please try again.")
    finally:
        if not owned:
            dest.unlink(missing_ok=True)
        await slot.__aexit__(None, None, None)

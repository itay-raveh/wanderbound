from __future__ import annotations

import asyncio
import io
import logging
import os
import secrets
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field
from pypdf import PdfWriter

from app.core.config import USER_COOKIE, settings

if TYPE_CHECKING:
    from playwright._impl._api_structures import PdfMargins
    from playwright.async_api import Browser, Page

    from app.models.ids import AlbumId
    from app.models.user import User

logger = logging.getLogger(__name__)

_pdf_semaphore = asyncio.Semaphore(1)

# Max pages per PDF chunk to stay under Chromium's V8 string size limit.
_CHUNK_SIZE = 30

_TOKEN_TTL = 300  # seconds before a download token expires


# ── SSE event models ──


class PdfQueued(BaseModel):
    type: Literal["queued"] = "queued"


class PdfProgress(BaseModel):
    type: Literal["progress"] = "progress"
    phase: Literal["loading", "rendering", "merging"]
    done: int
    total: int


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


# ── Download token store ──

_tokens: dict[str, Path] = {}


def _evict_token(token: str, path: Path) -> None:
    if _tokens.pop(token, None) is not None:
        path.unlink(missing_ok=True)
        logger.debug("Expired PDF token %s", token[:8])


def store_pdf_token(path: Path) -> str:
    token = secrets.token_urlsafe()
    _tokens[token] = path
    asyncio.get_running_loop().call_later(_TOKEN_TTL, _evict_token, token, path)
    return token


def pop_pdf_path(token: str) -> Path | None:
    return _tokens.pop(token, None)


# ── PDF rendering ──

_NO_MARGIN: PdfMargins = {"top": "0", "right": "0", "bottom": "0", "left": "0"}


async def _page_pdf(page: Page, *, page_ranges: str | None = None) -> bytes:
    return await page.pdf(
        prefer_css_page_size=True,
        print_background=True,
        margin=_NO_MARGIN,
        page_ranges=page_ranges,
    )


async def _generate_pdf_stream(
    page: Page, aid: AlbumId
) -> AsyncIterator[PdfProgress | bytes]:
    """Generate PDF in chunks, yielding progress events and final bytes."""
    total_pages = await page.evaluate(
        "document.querySelectorAll('.page-container').length"
    )
    logger.info("Album %s has %d print pages", aid, total_pages)

    if total_pages <= _CHUNK_SIZE:
        yield PdfProgress(phase="rendering", done=0, total=total_pages)
        pdf_bytes = await _page_pdf(page)
        yield PdfProgress(phase="rendering", done=total_pages, total=total_pages)
        logger.info("PDF generated for album %s: %d bytes", aid, len(pdf_bytes))
        yield pdf_bytes
        return

    chunks: list[bytes] = []

    for start in range(1, total_pages + 1, _CHUNK_SIZE):
        end = min(start + _CHUNK_SIZE - 1, total_pages)
        yield PdfProgress(phase="rendering", done=start - 1, total=total_pages)
        chunk = await _page_pdf(page, page_ranges=f"{start}-{end}")
        chunks.append(chunk)
        logger.info("PDF chunk pages %d-%d: %d bytes", start, end, len(chunk))

    yield PdfProgress(phase="rendering", done=total_pages, total=total_pages)

    # Merge chunks
    yield PdfProgress(phase="merging", done=0, total=1)
    writer = PdfWriter()
    for chunk in chunks:
        writer.append(io.BytesIO(chunk))

    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()
    yield PdfProgress(phase="merging", done=1, total=1)
    logger.info(
        "PDF generated for album %s: %d bytes (%d chunks)",
        aid,
        len(pdf_bytes),
        len(chunks),
    )
    yield pdf_bytes


async def render_album_pdf_stream(
    browser: Browser, user: User, aid: AlbumId, *, dark: bool = True
) -> AsyncIterator[PdfEvent]:
    """Top-level SSE generator: queued → loading → rendering → merging → done/error."""
    # Yield queued event while waiting for the semaphore
    yield PdfQueued()

    async with _pdf_semaphore:
        try:
            yield PdfProgress(phase="loading", done=0, total=1)

            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=2,
            )
            try:
                await context.add_cookies(
                    [
                        {
                            "name": USER_COOKIE,
                            "value": str(user.id),
                            "url": settings.FRONTEND_URL,
                        },
                    ]
                )
                page = await context.new_page()
                page.on("console", lambda msg: logger.debug("Browser: %s", msg.text))
                page.on(
                    "pageerror",
                    lambda err: logger.warning(
                        "Browser page error during PDF render: %s", err
                    ),
                )
                await page.emulate_media(media="print")
                dark_param = "true" if dark else "false"
                url = f"{settings.FRONTEND_URL}/print/{aid}?dark={dark_param}"
                await page.goto(url, wait_until="domcontentloaded")
                logger.info("DOM loaded for album %s", aid)
                await page.wait_for_function(
                    "window.__PRINT_READY__ === true", timeout=60_000
                )
                yield PdfProgress(phase="loading", done=1, total=1)

                # Stream rendering progress
                pdf_bytes: bytes | None = None
                async for item in _generate_pdf_stream(page, aid):
                    if isinstance(item, bytes):
                        pdf_bytes = item
                    else:
                        yield item

            finally:
                await context.close()

            # Write to temp file and issue a download token
            if pdf_bytes is None:
                yield PdfError(detail="PDF generation produced no output.")
                return
            fd, name = tempfile.mkstemp(suffix=".pdf", prefix="album_")
            os.close(fd)
            tmp_path = Path(name)
            await asyncio.to_thread(tmp_path.write_bytes, pdf_bytes)
            token = store_pdf_token(tmp_path)
            yield PdfDone(token=token)

        except Exception:
            logger.exception("PDF generation failed for album %s", aid)
            yield PdfError(detail="PDF generation failed. Please try again.")

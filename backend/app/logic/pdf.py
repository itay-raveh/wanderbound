from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING

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


async def render_album_pdf(
    browser: Browser, user: User, aid: AlbumId, *, dark: bool = True
) -> bytes:
    async with _pdf_semaphore:
        return await _render_album_pdf(browser, user, aid, dark=dark)


async def _render_album_pdf(
    browser: Browser, user: User, aid: AlbumId, *, dark: bool = True
) -> bytes:
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
            lambda err: logger.warning("Browser page error during PDF render: %s", err),
        )
        await page.emulate_media(media="print")
        url = f"{settings.FRONTEND_URL}/print/{aid}?dark={'true' if dark else 'false'}"
        await page.goto(url, wait_until="domcontentloaded")
        logger.info("DOM loaded for album %s", aid)
        await page.wait_for_function("window.__PRINT_READY__ === true", timeout=60_000)

        pdf_bytes = await _generate_pdf(page, aid)
    finally:
        await context.close()
    return pdf_bytes


_NO_MARGIN: PdfMargins = {"top": "0", "right": "0", "bottom": "0", "left": "0"}


async def _page_pdf(page: Page, *, page_ranges: str | None = None) -> bytes:
    return await page.pdf(
        prefer_css_page_size=True,
        print_background=True,
        margin=_NO_MARGIN,
        page_ranges=page_ranges,
    )


async def _generate_pdf(page: Page, aid: AlbumId) -> bytes:
    """Generate PDF, chunking by page ranges for large albums."""
    total_pages = await page.evaluate(
        "document.querySelectorAll('.page-container').length"
    )
    logger.info("Album %s has %d print pages", aid, total_pages)

    if total_pages <= _CHUNK_SIZE:
        pdf_bytes = await _page_pdf(page)
        logger.info("PDF generated for album %s: %d bytes", aid, len(pdf_bytes))
        return pdf_bytes

    # Generate in chunks to avoid Chromium's V8 string size limit.
    writer = PdfWriter()
    for start in range(1, total_pages + 1, _CHUNK_SIZE):
        end = min(start + _CHUNK_SIZE - 1, total_pages)
        chunk = await _page_pdf(page, page_ranges=f"{start}-{end}")
        writer.append(io.BytesIO(chunk))
        logger.info("PDF chunk pages %d-%d: %d bytes", start, end, len(chunk))

    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()
    logger.info(
        "PDF generated for album %s: %d bytes (%d chunks)",
        aid,
        len(pdf_bytes),
        (total_pages + _CHUNK_SIZE - 1) // _CHUNK_SIZE,
    )
    return pdf_bytes

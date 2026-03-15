import logging
from typing import TYPE_CHECKING

from app.core.config import USER_COOKIE, settings

if TYPE_CHECKING:
    from playwright.async_api import Browser

    from app.models.ids import AlbumId
    from app.models.user import User

logger = logging.getLogger(__name__)


async def render_album_pdf(
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
        # Activate @media print CSS before navigation so layout matches PDF output.
        await page.emulate_media(media="print")
        url = f"{settings.FRONTEND_URL}/print/{aid}?dark={'true' if dark else 'false'}"
        await page.goto(url, wait_until="domcontentloaded")
        logger.info("DOM loaded for album %s", aid)
        await page.wait_for_function("window.__PRINT_READY__ === true", timeout=60_000)
        pdf_bytes = await page.pdf(
            prefer_css_page_size=True,
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        logger.info("PDF generated for album %s: %d bytes", aid, len(pdf_bytes))
    finally:
        await context.close()
    return pdf_bytes

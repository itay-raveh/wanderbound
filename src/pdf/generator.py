"""PDF generation from HTML using Playwright."""

from pathlib import Path

from src.core.logger import get_logger
from src.core.settings import settings

logger = get_logger(__name__)

__all__ = ["generate_pdf"]


def generate_pdf(html_path: Path, pdf_path: Path) -> None:
    """Generate PDF file from HTML using Playwright.

    Opens the HTML file in a headless Chromium browser and exports it as a PDF
    with A4 landscape format. Requires Playwright to be installed.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        logger.info("Generating PDF from HTML...")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{html_path.absolute()}")
            page.wait_for_load_state("networkidle")
            # Using module-level settings
            page.set_viewport_size(
                {"width": settings.pdf.viewport_width, "height": settings.pdf.viewport_height}
            )

            page.pdf(
                path=str(pdf_path),
                format="A4",
                landscape=True,
                print_background=True,
                prefer_css_page_size=True,
            )
            browser.close()
        logger.info("PDF generated: %s", pdf_path, extra={"success": True})
    except ImportError:
        logger.warning("Playwright not installed. Install with: playwright install chromium")
        logger.info("Skipping PDF generation.")
    except Exception:
        logger.exception("Failed to generate PDF")
        logger.info("You can still open the HTML file in your browser and print to PDF manually.")

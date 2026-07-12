from __future__ import annotations

import re
import zipfile
from collections.abc import AsyncIterator
from contextlib import aclosing
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from app.logic.pdf import (
    PdfArtifact,
    PdfDone,
    PdfError,
    PdfEvent,
    PdfProgress,
    PdfQueued,
    PdfQueueTimeoutError,
    acquire_pdf_render_slot,
    pdf_queue_timeout_event,
    pdf_tokens,
    render_pdf_file,
    store_pdf_artifact,
)

if TYPE_CHECKING:
    from playwright.async_api import Browser
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.get_logger(__name__)


def chapter_pdf_member_names(chapter_ids: list[str]) -> list[str]:
    used: dict[str, int] = {}
    names: list[str] = []
    for index, chapter_id in enumerate(chapter_ids, start=1):
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", chapter_id).strip(".-_")
        if not stem:
            stem = f"chapter-{index}"
        count = used.get(stem, 0) + 1
        used[stem] = count
        suffix = "" if count == 1 else f"-{count}"
        names.append(f"{stem}{suffix}.pdf")
    return names


async def render_album_chapters_zip_stream(  # noqa: C901, PLR0913
    browser: Browser,
    session: AsyncSession,
    aid: str,
    chapter_ids: list[str],
    *,
    session_cookie: str,
    dark: bool = True,
) -> AsyncIterator[PdfEvent]:
    logger.info("pdf.chapter_zip_render_queued", album_id=aid)
    yield PdfQueued()
    if not chapter_ids:
        yield PdfError(detail="No chapters to export.")
        return

    try:
        slot = await acquire_pdf_render_slot(aid, "pdf.chapter_zip_queue_wait")
    except PdfQueueTimeoutError:
        yield pdf_queue_timeout_event()
        return

    zip_dest = pdf_tokens.make_dest(".zip")
    pdf_paths: list[Path] = []
    owned = False
    try:
        member_names = chapter_pdf_member_names(chapter_ids)
        with zipfile.ZipFile(zip_dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for index, (chapter_id, member_name) in enumerate(
                zip(chapter_ids, member_names, strict=True),
                start=1,
            ):
                pdf_dest = pdf_tokens.make_dest(".pdf")
                pdf_paths.append(pdf_dest)
                async with aclosing(
                    render_pdf_file(
                        browser,
                        aid,
                        pdf_dest,
                        session_cookie=session_cookie,
                        dark=dark,
                        chapter=chapter_id,
                    )
                ) as events:
                    async for event in events:
                        if isinstance(event, PdfProgress):
                            yield event
                if not pdf_dest.exists() or pdf_dest.stat().st_size == 0:
                    yield PdfError(detail="PDF generation produced no output.")
                    return
                zf.write(pdf_dest, member_name)
                yield PdfProgress(
                    phase="rendering",
                    done=index,
                    total=len(chapter_ids),
                )

        if zip_dest.stat().st_size == 0:
            yield PdfError(detail="Chapter ZIP generation produced no output.")
            return
        token = await store_pdf_artifact(
            session,
            PdfArtifact(
                path=zip_dest,
                filename=f"{aid}-chapters.zip",
                media_type="application/zip",
            ),
        )
        owned = True
        yield PdfDone(token=token)
    except Exception:
        logger.exception("pdf.chapter_zip_generation_failed", album_id=aid)
        yield PdfError(detail="Chapter ZIP generation failed. Please try again.")
    finally:
        for pdf_path in pdf_paths:
            pdf_path.unlink(missing_ok=True)
        if not owned:
            zip_dest.unlink(missing_ok=True)
        await slot.__aexit__(None, None, None)

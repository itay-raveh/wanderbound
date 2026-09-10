from asyncio import to_thread
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from app.logic.pdf import PdfDone, PdfProgress, pdf_tokens
from app.logic.pdf_chapters import render_album_chapters_zip_stream

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.mark.parametrize("separate", [False, True])
async def test_chapter_archive_preserves_each_selected_output(
    session: AsyncSession, *, separate: bool
) -> None:
    async def render(
        browser: object,
        aid: str,
        dest: Path,
        *,
        chapter: str,
        part: str,
        **kwargs: object,
    ) -> AsyncGenerator[PdfProgress]:
        content = f"{chapter}:{part}".encode()
        await to_thread(dest.write_bytes, content)
        yield PdfProgress(phase="rendering", done=len(content))

    @asynccontextmanager
    async def lock(*args: object) -> AsyncGenerator[bool]:
        yield True

    with (
        patch("app.logic.pdf_chapters.render_pdf_file", render),
        patch("app.logic.pdf.try_advisory_lock", lock),
    ):
        events = [
            event
            async for event in render_album_chapters_zip_stream(
                object(),
                session,
                "album",
                ["first", "second"],
                session_cookie="",
                separate=separate,
            )
        ]
    assert isinstance(events[-1], PdfDone)
    artifact = await pdf_tokens.pop(session, events[-1].token)
    assert artifact is not None
    try:
        with ZipFile(BytesIO(await to_thread(artifact.path.read_bytes))) as archive:
            expected = {
                (f"{chapter}/{part}.pdf" if separate else f"{chapter}.pdf"): (
                    f"{chapter}:{part}".encode()
                )
                for chapter in ("first", "second")
                for part in (("cover", "content") if separate else ("combined",))
            }
            assert {name: archive.read(name) for name in archive.namelist()} == expected
    finally:
        await to_thread(artifact.path.unlink, missing_ok=True)

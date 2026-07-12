import zipfile
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.logic import pdf, pdf_chapters
from tests.factories import collect_async


def write_fake_pdf(dest: Path, chapter: str | None) -> int:
    dest.write_bytes(f"pdf:{chapter}".encode())
    return dest.stat().st_size


def test_print_url_includes_chapter_when_requested() -> None:
    assert (
        pdf._print_url(
            "https://frontend.example/",
            "trip 1",
            dark=False,
            chapter="chapter 1",
        )
        == "https://frontend.example/print/trip%201?dark=false&chapter=chapter+1"
    )


def test_print_url_omits_chapter_for_full_album() -> None:
    assert (
        pdf._print_url("https://frontend.example", "trip-1", dark=True, chapter=None)
        == "https://frontend.example/print/trip-1?dark=true"
    )


async def test_render_album_chapters_zip_stream_creates_zip_artifact(
    session: Any,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    pdf.pdf_tokens.cleanup()

    @asynccontextmanager
    async def render_slot() -> AsyncGenerator[None]:
        yield

    async def acquire_slot(
        _aid: str,
        _span_name: str,
    ) -> AbstractAsyncContextManager[None]:
        slot = render_slot()
        await slot.__aenter__()
        return slot

    async def render_pdf(
        _browser: object,
        _aid: str,
        dest: Path,
        *,
        session_cookie: str,
        dark: bool,
        chapter: str | None = None,
    ) -> AsyncGenerator[pdf.PdfProgress]:
        assert session_cookie == "session-cookie"
        assert dark is False
        yield pdf.PdfProgress(phase="rendering", done=write_fake_pdf(dest, chapter))

    monkeypatch.setattr(pdf_chapters, "acquire_pdf_render_slot", acquire_slot)
    monkeypatch.setattr(pdf_chapters, "render_pdf_file", render_pdf)

    events = await collect_async(
        pdf_chapters.render_album_chapters_zip_stream(
            object(),
            session,
            "trip-1",
            ["chapter-one", "chapter-two"],
            session_cookie="session-cookie",
            dark=False,
        )
    )

    done = [event for event in events if isinstance(event, pdf.PdfDone)]
    assert len(done) == 1
    artifact = await pdf.pop_pdf_token(session, done[0].token)
    assert artifact is not None
    assert artifact.filename == "trip-1-chapters.zip"
    assert artifact.media_type == "application/zip"
    with zipfile.ZipFile(artifact.path) as zf:
        assert zf.namelist() == ["chapter-one.pdf", "chapter-two.pdf"]
        assert zf.read("chapter-one.pdf") == b"pdf:chapter-one"
        assert zf.read("chapter-two.pdf") == b"pdf:chapter-two"


def test_chapter_pdf_member_names_are_flat_unique_and_stable() -> None:
    assert pdf_chapters.chapter_pdf_member_names(["../Rome", "Rome", "a/b"]) == [
        "Rome.pdf",
        "Rome-2.pdf",
        "a-b.pdf",
    ]

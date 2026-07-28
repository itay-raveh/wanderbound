import zipfile
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.api.v1.routes import health
from app.core.config import get_settings
from app.logic import pdf, pdf_chapters
from tests.factories import collect_async


class FakeBrowser:
    def __init__(self) -> None:
        self.closed = False

    def is_connected(self) -> bool:
        return not self.closed

    async def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self) -> None:
        self.browsers: list[FakeBrowser] = []

    async def launch(self, *, args: list[str]) -> FakeBrowser:
        assert args == ["--use-gl=angle", "--no-sandbox"]
        browser = FakeBrowser()
        self.browsers.append(browser)
        return browser


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeChromium()
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class FakePlaywrightStarter:
    def __init__(self, runtimes: list[FakePlaywright]) -> None:
        self._runtimes = runtimes

    async def start(self) -> FakePlaywright:
        runtime = FakePlaywright()
        self._runtimes.append(runtime)
        return runtime


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


def test_render_capacity_uses_one_slot_per_available_cpu() -> None:
    assert pdf.render_capacity(0) == 1
    assert pdf.render_capacity(1) == 1
    assert pdf.render_capacity(4) == 4


async def test_pdf_browser_requests_use_public_url_as_referer(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    calls: dict[str, Any] = {}

    class PrintPageNavigatedError(Exception):
        pass

    class RecordingPage:
        def on(self, _event: str, _handler: object) -> None:
            pass

        async def emulate_media(self, *, media: str) -> None:
            calls["media"] = media

        async def goto(self, url: str, *, wait_until: str) -> None:
            calls["goto"] = (url, wait_until)
            raise PrintPageNavigatedError

    class RecordingContext:
        async def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
            calls["cookies"] = cookies

        async def new_page(self) -> RecordingPage:
            return RecordingPage()

        async def close(self) -> None:
            calls["closed"] = True

    class RecordingBrowser:
        async def new_context(self, **options: Any) -> RecordingContext:
            calls["context_options"] = options
            return RecordingContext()

    monkeypatch.setattr(
        pdf,
        "get_settings",
        lambda: SimpleNamespace(
            INTERNAL_URL="http://127.0.0.1:8000",
            PUBLIC_URL="https://wanderbound.example/",
        ),
    )
    stream = pdf.render_pdf_file(
        RecordingBrowser(),  # type: ignore[arg-type]
        "trip-1",
        tmp_path / "trip-1.pdf",
        session_cookie="session-cookie",
        dark=False,
    )

    assert await anext(stream) == pdf.PdfProgress(phase="loading", done=0)
    with pytest.raises(PrintPageNavigatedError):
        await anext(stream)

    assert calls["context_options"]["extra_http_headers"] == {
        "Referer": "https://wanderbound.example/"
    }
    assert calls["cookies"] == [
        {
            "name": "session",
            "value": "session-cookie",
            "url": "http://127.0.0.1:8000",
        }
    ]
    assert calls["goto"] == (
        "http://127.0.0.1:8000/print/trip-1?dark=false",
        "domcontentloaded",
    )
    assert calls["closed"] is True


async def test_render_queue_stops_waiting_after_one_minute(monkeypatch: Any) -> None:
    class Clock:
        now = 0.0

        def time(self) -> float:
            return self.now

    class UnavailableLock:
        async def __aenter__(self) -> bool:
            return False

        async def __aexit__(self, *_args: object) -> None:
            return None

    clock = Clock()

    async def advance(seconds: float) -> None:
        clock.now += seconds

    monkeypatch.setattr(pdf.asyncio, "get_running_loop", lambda: clock)
    monkeypatch.setattr(pdf.asyncio, "sleep", advance)
    monkeypatch.setattr(pdf, "try_advisory_lock", lambda _name: UnavailableLock())
    monkeypatch.setattr(pdf, "_max_concurrent", 1)

    with pytest.raises(TimeoutError):
        async with pdf.render_pdf_slot():
            pytest.fail("queue acquired unavailable capacity")

    assert clock.now == 60


async def test_browser_manager_shares_browser_until_last_lease_closes(
    monkeypatch: Any,
) -> None:
    runtimes: list[FakePlaywright] = []
    monkeypatch.setattr(
        pdf,
        "async_playwright",
        lambda: FakePlaywrightStarter(runtimes),
    )
    manager = pdf.BrowserManager()

    first_lease = manager.acquire()
    first_browser = await first_lease.__aenter__()
    second_lease = manager.acquire()
    second_browser = await second_lease.__aenter__()

    assert first_browser is second_browser
    assert len(runtimes) == 1
    await first_lease.__aexit__(None, None, None)
    assert first_browser.is_connected()
    assert not runtimes[0].stopped

    await second_lease.__aexit__(None, None, None)
    assert not first_browser.is_connected()
    assert runtimes[0].stopped


async def test_browser_manager_probe_is_healthy_without_idle_runtime(
    monkeypatch: Any,
) -> None:
    runtimes: list[FakePlaywright] = []
    monkeypatch.setattr(
        pdf,
        "async_playwright",
        lambda: FakePlaywrightStarter(runtimes),
    )
    manager = pdf.BrowserManager()

    await manager.probe()

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(browser_manager=manager),
        )
    )
    assert health._check_playwright(request)
    assert len(runtimes) == 1
    assert not runtimes[0].chromium.browsers[0].is_connected()
    assert runtimes[0].stopped


async def test_render_album_pdf_stream_reports_high_load_without_rendering(
    session: Any,
    monkeypatch: Any,
) -> None:
    async def capacity_timeout(
        _aid: str,
        _span_name: str,
    ) -> AbstractAsyncContextManager[None]:
        raise pdf.PdfQueueTimeoutError

    monkeypatch.setattr(pdf, "acquire_pdf_render_slot", capacity_timeout)

    events = await collect_async(
        pdf.render_album_pdf_stream(
            object(),
            session,
            "trip-1",
            session_cookie="session-cookie",
        )
    )

    assert events == [pdf.PdfQueued(), pdf.PdfBusy()]


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

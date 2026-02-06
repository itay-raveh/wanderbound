"""Logging configuration for the album generator using Rich."""

from __future__ import annotations

import logging
import logging.handlers
from typing import IO

from nicegui import context
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from .settings import settings

_console: Console = Console()


def get_console() -> Console:
    return _console


def set_console(console: Console) -> None:
    """Set the global console instance for all progress bars and logging."""
    global _console  # noqa: PLW0603
    _console = console


# noinspection PyAbstractClass
class TeeIO(IO[str]):
    """A file-like object that writes to multiple files."""

    def __init__(self, *files: IO[str]) -> None:
        self.files = files

    def write(self, s: str, /) -> int:  # type: ignore[override]
        for f in self.files:
            f.write(s)
        return len(s)

    def flush(self) -> None:
        for f in self.files:
            f.flush()

    def isatty(self) -> bool:
        return any(getattr(f, "isatty", lambda: False)() for f in self.files)


class RichPrintHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Check if this is a success message via extra keyword argument
        is_success = getattr(record, "success", False)

        output = self.format(record)

        # Apply icons
        if is_success:
            output = "✓ " + output
        elif record.levelno == logging.WARNING:
            output = "⚠ " + output
        elif record.levelno >= logging.ERROR:
            output = "✗ " + output

        # Apply colors
        if is_success:
            output = f"[green]{output}[/green]"
        elif record.levelno == logging.WARNING:
            output = f"[yellow]{output}[/yellow]"
        elif record.levelno >= logging.ERROR:
            output = f"[red]{output}[/red]"

        get_console().print(output)


_LOG_LEVEL = logging.DEBUG if settings.debug else logging.INFO


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    # Console Handler
    console_handler = RichHandler() if settings.debug else RichPrintHandler()
    console_handler.setLevel(_LOG_LEVEL)

    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)

    # Custom Filter to inject session ID
    class SessionFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            try:
                client = context.get_client()
                record.session_id = str(client.id) if client else "-"
            except (RuntimeError, AttributeError):  # Raised if not in a NiceGUI request context
                record.session_id = "-"
            return True

    file_handler.addFilter(SessionFilter())

    # Format with session ID
    formatter = logging.Formatter(
        "%(asctime)s - [%(session_id)s] - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)

    logger.setLevel(_LOG_LEVEL)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logger.propagate = False

    return logger


def create_progress(title: str | None = None, spinner: str = "dots") -> Progress:
    # Use fixed-width format to align all progress bars regardless of title length
    progress = Progress(
        SpinnerColumn(spinner),
        TextColumn("[progress.description]{task.description:<30}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(compact=True, elapsed_when_finished=True),
        console=get_console(),
    )

    if title:
        progress.print(Panel.fit(title))

    return progress

"""Logging configuration for the album generator using Rich."""

import logging

from rich import print as rprint
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from .settings import settings

_LOG_LEVEL = logging.DEBUG if settings.debug else logging.INFO


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

        rprint(output)


_HANDLER: logging.Handler
if settings.debug:
    _HANDLER = RichHandler(
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        markup=True,
    )
else:
    _HANDLER = RichPrintHandler()

_HANDLER.setLevel(_LOG_LEVEL)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(_LOG_LEVEL)
    logger.addHandler(_HANDLER)
    logger.propagate = False

    return logger


def create_progress() -> Progress:
    # Use fixed-width format to align all progress bars regardless of title length
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description:<70}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        transient=True,
    )

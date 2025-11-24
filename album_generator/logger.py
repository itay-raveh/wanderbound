"""Logging configuration for the album generator using Rich."""

import logging

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from .settings import get_settings

# Default log level
DEFAULT_LOG_LEVEL = logging.INFO

# Get settings
_settings = get_settings()
DEBUG_MODE = _settings.debug

# Set log level based on DEBUG setting
LOG_LEVEL = logging.DEBUG if DEBUG_MODE else DEFAULT_LOG_LEVEL

# Global console instance with markup enabled
_console = Console(markup=True)


class PrettyCLIHandler(logging.Handler):
    """Custom handler that formats log messages as pretty CLI output (non-debug mode)."""

    def __init__(self, console: Console):
        super().__init__()
        self.console = console
        self.level_map = {
            logging.INFO: "",
            logging.WARNING: "⚠",
            logging.ERROR: "✗",
            logging.CRITICAL: "✗",
            logging.DEBUG: "•",
        }

    def emit(self, record: logging.LogRecord) -> None:
        """Format and emit a log record."""
        try:
            message = self.format(record)

            # Check if this is a success message via extra keyword argument
            is_success = getattr(record, "success", False)
            if record.levelno == logging.INFO and is_success:
                level_icon = "✓"
            else:
                level_icon = self.level_map.get(record.levelno, "•")

            # Just add icon and print as normal string - let Rich handle everything else
            output = f"{level_icon} {message}" if level_icon else message

            # Apply colors based on log level
            if is_success and record.levelno == logging.INFO:
                output = f"[green]{output}[/green]"
            elif record.levelno == logging.ERROR or record.levelno == logging.CRITICAL:
                output = f"[red]{output}[/red]"
            elif record.levelno == logging.WARNING:
                output = f"[yellow]{output}[/yellow]"

            self.console.print(output, markup=True)
        except Exception:
            self.handleError(record)


def setup_logging(name: str = "album_generator") -> logging.Logger:
    """Set up and return a logger instance."""
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(LOG_LEVEL)

        if DEBUG_MODE:
            # Debug mode: use RichHandler with its default automatic colors
            handler: logging.Handler = RichHandler(
                console=_console,
                show_path=True,
                show_time=True,
                show_level=True,
                rich_tracebacks=True,
                tracebacks_show_locals=True,
                markup=True,
                log_time_format="%H:%M:%S",
            )
        else:
            # Non-debug mode: use custom handler for pretty CLI output
            handler = PrettyCLIHandler(_console)

        handler.setLevel(LOG_LEVEL)
        logger.addHandler(handler)

        # Prevent propagation to root logger
        logger.propagate = False

    return logger


def get_logger(name: str = "album_generator") -> logging.Logger:
    """Get a logger instance. Pass __name__ from the calling module."""
    return setup_logging(name)


def get_console() -> Console:
    """Get the global console instance."""
    return _console


def create_progress(
    description: str = "Processing", total: int | None = None
) -> Progress:
    """Create a Rich progress bar for loops with aligned descriptions."""
    # Use fixed-width format to align all progress bars regardless of title length
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description:<70}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=_console,
    )


# Export DEBUG_MODE for use in other modules
__all__ = [
    "get_logger",
    "get_console",
    "create_progress",
    "DEBUG_MODE",
]

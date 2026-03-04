"""Logging configuration for the album generator using Rich."""

from __future__ import annotations

import logging
import logging.handlers

from rich.logging import RichHandler

from .settings import settings

_LOG_LEVEL = logging.INFO


def config_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        "[%(asctime)s][%(name)s][%(levelname)s] %(message)s"
    )
    file_handler.setFormatter(formatter)

    logger.setLevel(_LOG_LEVEL)
    logger.addHandler(
        RichHandler(
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            markup=True,
        )
    )
    logger.addHandler(file_handler)

    logger.propagate = False

    return logger

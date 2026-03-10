from __future__ import annotations

import logging

from rich.logging import RichHandler

_LOG_LEVEL = logging.INFO


def config_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(_LOG_LEVEL)
    logger.addHandler(
        RichHandler(
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            markup=True,
        )
    )

    logger.propagate = False

    return logger

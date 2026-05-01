import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from asgi_correlation_id import correlation_id

_NOISY = (
    "sqlalchemy.engine",
    "httpx",
    "httpcore",
    "hishel",
    "PIL",
    "playwright",
)

# Loggers that should print to terminal but not propagate to Sentry.
# Sentry's LoggingIntegration is configured to skip these in main.py.
SENTRY_IGNORED = ("uvicorn.access",)
_ACCESS_LOG_HEALTH_PATHS = {"/api/v1/health"}


class _HealthAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        path = _uvicorn_access_path(record)
        return path not in _ACCESS_LOG_HEALTH_PATHS


def _add_request_id(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    if request_id := correlation_id.get():
        event_dict["request_id"] = request_id
    return event_dict


def _drop_color_message_key(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    event_dict.pop("color_message", None)
    return event_dict


def _uvicorn_access_path(record: logging.LogRecord) -> str | None:
    args = record.args
    if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
        return args[2]
    return None


def setup_logging(*, use_console: bool, log_level: str = "INFO") -> None:
    level = getattr(logging, log_level.upper())
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[structlog.types.Processor] = [
        _add_request_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        _drop_color_message_key,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]
    exception_processors: list[structlog.types.Processor] = []

    renderer: structlog.types.Processor
    if use_console:
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )
    else:
        exception_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            *exception_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[*shared_processors, *exception_processors],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
    logging.getLogger("app").setLevel(level)

    logging.getLogger("uvicorn").setLevel(logging.INFO)
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.setLevel(logging.INFO)
    access_logger.filters = [
        f for f in access_logger.filters if not isinstance(f, _HealthAccessFilter)
    ]
    access_logger.addFilter(_HealthAccessFilter())
    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

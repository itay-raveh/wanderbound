import json
import logging
import sys
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        entry = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


_NOISY = ("sqlalchemy.engine", "httpx", "httpcore", "hishel", "PIL", "playwright")


def setup_logging(*, environment: str) -> None:
    if environment == "local":
        from rich.logging import RichHandler  # noqa: PLC0415

        handler = RichHandler(rich_tracebacks=True, markup=True)
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JSONFormatter())

    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
    logging.getLogger("app").setLevel(logging.INFO)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)

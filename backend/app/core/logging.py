import http
import logging

from rich.logging import RichHandler


class AccessHandler(RichHandler):
    """Format uvicorn access log records with colored status codes."""

    def emit(self, record: logging.LogRecord) -> None:
        if isinstance(record.args, tuple) and len(record.args) == 5:
            addr, method, path, _http_ver, status_code = record.args
            code = int(status_code)  # type: ignore[arg-type]
            color = "on red" if code >= 400 else "on green"
            record.msg = "[%s] %-5s %s [%s] %s %s [/]"
            record.args = (
                addr,
                method,
                path,
                color,
                code,
                http.HTTPStatus(code).phrase,
            )
        super().emit(record)

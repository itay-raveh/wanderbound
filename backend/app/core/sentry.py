import logging
from collections.abc import Callable
from fnmatch import fnmatch
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import sentry_sdk
from sentry_sdk.integrations.logging import (
    LoggingIntegration,
    ignore_logger,
    ignore_logger_for_sentry_logs,
)
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint, Log, SamplingContext

    from app.core.config import Settings

SENTRY_IGNORED_LOGGERS = ("uvicorn.access",)
SENTRY_LOG_IGNORED_LOGGERS = (
    *SENTRY_IGNORED_LOGGERS,
    "sqlalchemy.engine*",
    "httpx*",
    "httpcore*",
    "hishel*",
    "PIL*",
    "playwright*",
)
SENTRY_TRACE_IGNORED_PATHS = {"/api/v1/health"}
SENTRY_INFO_LOG_EVENTS = {
    "auth.sign_in",
    "eviction.completed",
    "export.ready",
    "google_photos.upgrade.completed",
    "pdf.generated",
    "processing.completed",
    "upload.completed",
}


def setup_sentry(settings: Settings) -> None:
    if not _sentry_enabled(settings):
        return

    for name in SENTRY_IGNORED_LOGGERS:
        ignore_logger(name)
    for name in SENTRY_LOG_IGNORED_LOGGERS:
        ignore_logger_for_sentry_logs(name)

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=settings.APP_VERSION,
        traces_sampler=_traces_sampler(settings),
        trace_propagation_targets=[],
        trace_ignore_status_codes={404},
        before_send_transaction=_before_send_transaction,
        enable_logs=True,
        before_send_log=_before_send_log,
        integrations=[
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
                sentry_logs_level=logging.INFO,
            )
        ],
        before_breadcrumb=_before_breadcrumb,
        include_local_variables=False,
        max_request_body_size="never",
        send_default_pii=False,
        event_scrubber=EventScrubber(
            denylist=[
                *DEFAULT_DENYLIST,
                "access_token",
                "refresh_token",
                "code_verifier",
                "verifier",
                "credential",
            ],
            recursive=True,
        ),
    )


def _sentry_enabled(settings: Settings) -> bool:
    return settings.ENVIRONMENT == "production" and bool(settings.SENTRY_DSN)


def _before_breadcrumb(crumb: dict, _hint: dict) -> dict | None:
    if crumb.get("category") in SENTRY_IGNORED_LOGGERS:
        return None
    return crumb


def _before_send_log(log: Log, _hint: Hint) -> Log | None:
    attrs = log.get("attributes") or {}
    logger_name = attrs.get("logger.name")
    if isinstance(logger_name, str) and any(
        fnmatch(logger_name, name) for name in SENTRY_LOG_IGNORED_LOGGERS
    ):
        return None

    severity = log.get("severity_text")
    if severity in {"warn", "error", "fatal"}:
        return log
    if severity == "info" and attrs.get("event") in SENTRY_INFO_LOG_EVENTS:
        return log
    return None


def _traces_sampler(settings: Settings) -> Callable[[SamplingContext], float | bool]:
    def sampler(sampling_context: SamplingContext) -> float | bool:
        transaction_context = sampling_context.get("transaction_context") or {}
        transaction_name = transaction_context.get("name")
        if isinstance(transaction_name, str):
            for path in SENTRY_TRACE_IGNORED_PATHS:
                if path in transaction_name:
                    return 0

        if sampling_context.get("parent_sampled") is not None:
            return sampling_context["parent_sampled"]

        return settings.SENTRY_TRACES_SAMPLE_RATE

    return sampler


def _before_send_transaction(event: Event, _hint: Hint) -> Event | None:
    request = event.get("request") or {}
    url = request.get("url")
    path = urlparse(url).path if isinstance(url, str) else None
    if path in SENTRY_TRACE_IGNORED_PATHS:
        return None
    return event

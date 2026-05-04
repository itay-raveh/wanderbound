from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import sentry_sdk

if TYPE_CHECKING:
    from sentry_sdk.tracing import Span


def set_span_data(span: Span | None, **data: Any) -> None:
    if span is None:
        return
    for key, value in data.items():
        if value is not None:
            span.set_data(key, value)


@contextmanager
def start_span(op: str, name: str, **data: Any) -> Iterator[Span]:
    with sentry_sdk.start_span(op=op, name=name) as span:
        set_span_data(span, **data)
        yield span

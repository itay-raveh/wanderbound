from typing import TYPE_CHECKING

from app.core import resources

if TYPE_CHECKING:
    import pytest


def test_detect_cpu_count_uses_container_aware_joblib(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resources.detect_cpu_count.cache_clear()
    monkeypatch.setattr(resources, "joblib_cpu_count", lambda: 2, raising=False)
    monkeypatch.setattr(resources.os, "process_cpu_count", lambda: 8)

    try:
        assert resources.detect_cpu_count() == 2
    finally:
        resources.detect_cpu_count.cache_clear()

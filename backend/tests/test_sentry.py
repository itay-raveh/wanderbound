from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

from app.core import sentry
from app.core.config import PublicSettings


def test_setup_sentry_uses_a_package_semver_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    settings = SimpleNamespace(
        ENVIRONMENT="production",
        SENTRY_DSN="https://public@example.invalid/1",
        APP_VERSION="v1.7.0",
        SENTRY_TRACES_SAMPLE_RATE=PublicSettings().SENTRY_TRACES_SAMPLE_RATE,
    )
    monkeypatch.setattr(
        sentry.sentry_sdk, "init", lambda **values: captured.update(values)
    )

    sentry.setup_sentry(settings)  # type: ignore[arg-type]

    assert captured["release"] == "wanderbound@1.7.0"

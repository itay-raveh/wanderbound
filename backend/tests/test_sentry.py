from app.core.sentry import sentry_release


def test_sentry_release_uses_package_semver() -> None:
    assert sentry_release("v1.7.0") == "wanderbound@1.7.0"
    assert sentry_release("1.7.0") == "wanderbound@1.7.0"
    assert sentry_release("v1.7.0-5-g5bd3780e") == "wanderbound@1.7.0-5-g5bd3780e"
    assert sentry_release(None) is None

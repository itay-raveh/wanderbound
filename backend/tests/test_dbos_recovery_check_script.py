import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self
from urllib.request import Request

if TYPE_CHECKING:
    import pytest


def _load_check_module() -> Any:
    script_path = Path(__file__).parents[2] / "scripts" / "dbos_recovery_check.py"
    spec = importlib.util.spec_from_file_location("dbos_recovery_check", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalizes_sqlalchemy_psycopg_url_for_psycopg() -> None:
    module = _load_check_module()

    assert (
        module.psycopg_url("postgresql+psycopg://postgres:postgres@localhost/app")
        == "postgresql://postgres:postgres@localhost/app"
    )
    assert (
        module.psycopg_url("postgresql://postgres:postgres@localhost/app")
        == "postgresql://postgres:postgres@localhost/app"
    )


def test_dbos_config_uses_postgres_system_schema_and_executor_id() -> None:
    module = _load_check_module()

    config = module.dbos_recovery_config(
        "postgresql+psycopg://postgres:postgres@localhost/app",
        executor_id="worker-b",
    )

    assert config["name"] == "wanderbound-dbos-check"
    assert (
        config["system_database_url"]
        == "postgresql+psycopg://postgres:postgres@localhost/app"
    )
    assert config["executor_id"] == "worker-b"
    assert config["dbos_system_schema"] == "dbos_recovery_check"
    assert config["run_admin_server"] is False


def test_admin_recovery_posts_executor_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_check_module()
    calls = []

    class FakeResponse:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(["workflow-1"]).encode()

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        calls.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    assert module.recover_workflows_via_admin(
        "http://127.0.0.1:3001", ["worker-a"]
    ) == ["workflow-1"]
    request, timeout = calls[0]
    assert request.full_url == "http://127.0.0.1:3001/dbos-workflow-recovery"
    assert request.method == "POST"
    assert request.data == b'["worker-a"]'
    assert request.headers["Content-type"] == "application/json"
    assert timeout == 30

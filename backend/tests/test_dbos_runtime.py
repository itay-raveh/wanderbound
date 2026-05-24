from typing import Any
from unittest.mock import patch

from pydantic import SecretStr

from app.logic.workflows.runtime import dbos_config, destroy_dbos, launch_dbos


class _Settings:
    DBOS_APP_NAME = "wanderbound"
    DBOS_SYSTEM_DATABASE_URI = None
    DBOS_EXECUTOR_ID: str | None = "worker-1"
    DBOS_ADMIN_PORT = 3001
    DBOS_RUN_ADMIN_SERVER = True
    DBOS_HEARTBEAT_TTL_SECONDS = 60.0
    DBOS_RECOVERY_INTERVAL_SECONDS = 10.0
    SQLALCHEMY_DATABASE_URI = "postgresql+psycopg://app:secret@db/app"
    LOG_LEVEL = "INFO"


def test_dbos_config_uses_app_database_by_default() -> None:
    assert dbos_config(_Settings()) == {
        "name": "wanderbound",
        "system_database_url": "postgresql+psycopg://app:secret@db/app",
        "run_admin_server": True,
        "admin_port": 3001,
        "executor_id": "worker-1",
        "log_level": "INFO",
    }


def test_dbos_config_accepts_admin_server_override() -> None:
    assert dbos_config(_Settings(), run_admin_server=False)["run_admin_server"] is False


def test_dbos_config_accepts_dedicated_system_database() -> None:
    settings = _Settings()
    settings.DBOS_SYSTEM_DATABASE_URI = SecretStr(
        "postgresql+psycopg://dbos:secret@db/dbos"
    )

    assert dbos_config(settings)["system_database_url"] == (
        "postgresql+psycopg://dbos:secret@db/dbos"
    )


def test_launch_and_destroy_dbos_delegate_to_dbos_runtime() -> None:
    settings = _Settings()
    with (
        patch("app.logic.workflows.runtime.DBOS") as dbos,
        patch(
            "app.logic.workflows.runtime.dbos_config", return_value={"name": "x"}
        ) as dbos_config_mock,
    ):
        launch_dbos(settings, run_admin_server=False)
        destroy_dbos()

    dbos_config_mock.assert_called_once_with(settings, run_admin_server=False)
    dbos.assert_called_once_with(config={"name": "x"})
    dbos.launch.assert_called_once_with()
    dbos.destroy.assert_called_once_with(workflow_completion_timeout_sec=5)


def test_dbos_config_generates_executor_id_when_unset(monkeypatch: Any) -> None:
    settings = _Settings()
    settings.DBOS_EXECUTOR_ID = None
    monkeypatch.setattr(
        "app.logic.workflows.recovery.socket.gethostname", lambda: "host"
    )
    monkeypatch.setattr("app.logic.workflows.recovery.os.getpid", lambda: 123)

    assert dbos_config(settings)["executor_id"] == "host-123"

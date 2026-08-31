from types import SimpleNamespace

from app.logic.workflows.runtime import dbos_config


def test_dbos_config_uses_stable_executor_without_admin_server() -> None:
    settings = SimpleNamespace(
        DBOS_APP_NAME="wanderbound",
        DBOS_SYSTEM_DATABASE_URI=None,
        DBOS_EXECUTOR_ID="local",
        LOG_LEVEL="INFO",
        SQLALCHEMY_DATABASE_URI="postgresql://app@database/wanderbound",
    )

    config = dbos_config(settings)

    assert config["executor_id"] == "local"
    assert config["run_admin_server"] is False
    assert "admin_port" not in config

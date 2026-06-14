from typing import Any, cast

from dbos import DBOS
from pydantic import SecretStr

from app.logic.workflows.recovery import workflow_executor_id


def _database_url(value: object) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return str(value)


def _database_url_or_none(value: object) -> str | None:
    if value is None:
        return None
    url = _database_url(value)
    return url or None


def dbos_config(
    settings: Any, *, run_admin_server: bool | None = None
) -> dict[str, Any]:
    system_database_url = (
        _database_url_or_none(settings.DBOS_SYSTEM_DATABASE_URI)
        or settings.SQLALCHEMY_DATABASE_URI
    )
    config: dict[str, Any] = {
        "name": settings.DBOS_APP_NAME,
        "system_database_url": _database_url(system_database_url),
        "run_admin_server": (
            settings.DBOS_RUN_ADMIN_SERVER
            if run_admin_server is None
            else run_admin_server
        ),
        "admin_port": settings.DBOS_ADMIN_PORT,
        "log_level": settings.LOG_LEVEL,
    }
    config["executor_id"] = workflow_executor_id(settings)
    return config


def launch_dbos(settings: Any, *, run_admin_server: bool | None = None) -> None:
    DBOS(config=cast("Any", dbos_config(settings, run_admin_server=run_admin_server)))
    DBOS.launch()


def destroy_dbos() -> None:
    DBOS.destroy(workflow_completion_timeout_sec=5)

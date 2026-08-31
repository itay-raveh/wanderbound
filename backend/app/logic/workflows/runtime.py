from typing import Any, cast

from dbos import DBOS
from pydantic import SecretStr

from app.logic.workflows.media_hashes import MEDIA_HASH_QUEUE


def _database_url(value: object) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return str(value)


def _database_url_or_none(value: object) -> str | None:
    if value is None:
        return None
    url = _database_url(value)
    return url or None


def dbos_config(settings: Any) -> dict[str, Any]:
    system_database_url = (
        _database_url_or_none(settings.DBOS_SYSTEM_DATABASE_URI)
        or settings.SQLALCHEMY_DATABASE_URI
    )
    return {
        "name": settings.DBOS_APP_NAME,
        "system_database_url": _database_url(system_database_url),
        "run_admin_server": False,
        "log_level": settings.LOG_LEVEL,
        "executor_id": settings.DBOS_EXECUTOR_ID,
    }


async def launch_dbos(settings: Any) -> None:
    DBOS(config=cast("Any", dbos_config(settings)))
    DBOS.launch()
    await DBOS.register_queue_async(MEDIA_HASH_QUEUE, worker_concurrency=1)


def destroy_dbos() -> None:
    DBOS.destroy(workflow_completion_timeout_sec=5)

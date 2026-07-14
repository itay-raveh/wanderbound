import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

from app.logic.segment_routes import get_route_enrichment_http_clients
from app.logic.workflows.processing import get_processing_workflow_http_clients
from app.main import lifespan, settings

if TYPE_CHECKING:
    import pytest


@asynccontextmanager
async def _yielding(value: object = None) -> AsyncIterator[object]:
    yield value


async def _forever(*_args: object, **_kwargs: object) -> None:
    await asyncio.Event().wait()


async def test_lifespan_initializes_workflow_clients_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    http = object()
    app = SimpleNamespace(state=SimpleNamespace())
    launch_calls: list[bool | None] = []

    def locked(_key: str) -> object:
        acquired = True
        return _yielding(acquired)

    def browser_lifespan() -> object:
        return _yielding("browser")

    def http_lifespan() -> object:
        return _yielding(http)

    def launch(_settings: object, *, run_admin_server: bool | None = None) -> None:
        get_processing_workflow_http_clients()
        get_route_enrichment_http_clients()
        launch_calls.append(run_admin_server)

    upload_store = SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(settings, "DATA_FOLDER", tmp_path)
    monkeypatch.setattr(settings, "DBOS_RUN_ADMIN_SERVER", True)
    monkeypatch.setattr("app.main.cleanup_orphaned_tmp", _noop_cleanup)
    monkeypatch.setattr("app.main.try_advisory_lock", locked)
    monkeypatch.setattr("app.main.pdf_lifespan", browser_lifespan)
    monkeypatch.setattr("app.main.export_lifespan", _yielding)
    monkeypatch.setattr("app.main.undo_lifespan", _yielding)
    monkeypatch.setattr("app.main.build_upload_store", lambda _settings: upload_store)
    monkeypatch.setattr("app.main.lifespan_clients", http_lifespan)
    monkeypatch.setattr("app.main.launch_dbos", launch)
    monkeypatch.setattr("app.main.destroy_dbos", lambda: None)
    monkeypatch.setattr("app.main.workflow_heartbeat_loop", _forever)
    monkeypatch.setattr("app.main.workflow_recovery_loop", _forever)
    monkeypatch.setattr("app.main.upload_cleanup_loop", _forever)

    async with lifespan(app):
        assert app.state.http is http
        assert app.state.upload_store is upload_store

    assert launch_calls == [True]


async def _noop_cleanup(_path: Path) -> None:
    return None

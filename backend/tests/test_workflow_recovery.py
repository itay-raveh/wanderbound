from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Self
from urllib.request import Request

from app.logic.workflows.recovery import (
    WORKFLOW_RECOVERY_PATH,
    WorkflowAdminState,
    list_dead_workflow_executors,
    record_workflow_executor_heartbeat,
    recover_dead_workflow_executors,
    recover_workflows_via_admin,
    workflow_admin_election_once,
    workflow_heartbeat_once,
)
from app.models.processing import WorkflowExecutorHeartbeat

if TYPE_CHECKING:
    import pytest
    from sqlmodel.ext.asyncio.session import AsyncSession


async def test_records_executor_heartbeat(session: AsyncSession) -> None:
    await record_workflow_executor_heartbeat(
        session,
        executor_id="worker-1",
        admin_base_url="http://127.0.0.1:3001",
    )

    row = await session.get(WorkflowExecutorHeartbeat, "worker-1")

    assert row is not None
    assert row.admin_base_url == "http://127.0.0.1:3001"
    assert row.status == "active"


async def test_records_non_admin_executor_heartbeat(session: AsyncSession) -> None:
    await record_workflow_executor_heartbeat(
        session,
        executor_id="worker-2",
        admin_base_url=None,
    )

    row = await session.get(WorkflowExecutorHeartbeat, "worker-2")

    assert row is not None
    assert row.admin_base_url == ""
    assert row.status == "active"


async def test_list_dead_executors_marks_stale_active_rows_dead(
    session: AsyncSession,
) -> None:
    stale = WorkflowExecutorHeartbeat(
        executor_id="stale-worker",
        admin_base_url="http://127.0.0.1:3001",
        status="active",
        last_seen_at=datetime.now(UTC) - timedelta(seconds=120),
    )
    current = WorkflowExecutorHeartbeat(
        executor_id="current-worker",
        admin_base_url="http://127.0.0.1:3001",
        status="active",
        last_seen_at=datetime.now(UTC),
    )
    already_dead = WorkflowExecutorHeartbeat(
        executor_id="dead-worker",
        admin_base_url="http://127.0.0.1:3001",
        status="dead",
        last_seen_at=datetime.now(UTC) - timedelta(seconds=120),
    )
    session.add_all([stale, current, already_dead])
    await session.flush()

    dead = await list_dead_workflow_executors(
        session, stale_after=timedelta(seconds=60)
    )

    assert dead == ["stale-worker"]
    assert stale.status == "dead"
    assert current.status == "active"
    assert already_dead.status == "dead"


def test_recover_workflows_via_admin_posts_executor_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Request, float]] = []

    class FakeResponse:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'["workflow-1"]'

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        calls.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr("app.logic.workflows.recovery.urlopen", fake_urlopen)

    assert recover_workflows_via_admin("http://127.0.0.1:3001", ["stale-worker"]) == [
        "workflow-1"
    ]

    request, timeout = calls[0]
    assert request.full_url == f"http://127.0.0.1:3001{WORKFLOW_RECOVERY_PATH}"
    assert request.method == "POST"
    assert request.data == b'["stale-worker"]'
    assert request.headers["Content-type"] == "application/json"
    assert timeout == 30


class _RecoverySettings:
    DBOS_EXECUTOR_ID = "current-worker"
    DBOS_ADMIN_PORT = 3001
    DBOS_HEARTBEAT_TTL_SECONDS = 60.0
    DBOS_RECOVERY_INTERVAL_SECONDS = 10.0


async def test_workflow_heartbeat_once_records_current_executor(
    session: AsyncSession,
) -> None:
    await workflow_heartbeat_once(session, _RecoverySettings(), has_admin_server=False)

    current = await session.get(WorkflowExecutorHeartbeat, "current-worker")
    assert current is not None
    assert current.admin_base_url == ""
    assert current.status == "active"


async def test_recover_dead_workflow_executors_recovers_stale(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = WorkflowExecutorHeartbeat(
        executor_id="stale-worker",
        admin_base_url="http://127.0.0.1:3001",
        status="active",
        last_seen_at=datetime.now(UTC) - timedelta(seconds=120),
    )
    session.add(stale)
    await session.flush()
    calls: list[tuple[str, list[str]]] = []

    def fake_recover(admin_base_url: str, executor_ids: list[str]) -> list[str]:
        calls.append((admin_base_url, executor_ids))
        return ["workflow-1"]

    monkeypatch.setattr(
        "app.logic.workflows.recovery.recover_workflows_via_admin",
        fake_recover,
    )

    recovered = await recover_dead_workflow_executors(session, _RecoverySettings())

    assert stale.status == "dead"
    assert recovered == ["workflow-1"]
    assert calls == [("http://127.0.0.1:3001", ["stale-worker"])]


async def test_recover_dead_workflow_executors_runs_admin_call_in_thread(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = WorkflowExecutorHeartbeat(
        executor_id="stale-worker",
        admin_base_url="http://127.0.0.1:3001",
        status="active",
        last_seen_at=datetime.now(UTC) - timedelta(seconds=120),
    )
    session.add(stale)
    await session.flush()
    calls: list[tuple[object, tuple[object, ...]]] = []

    async def fake_to_thread(func: object, *args: object) -> list[str]:
        calls.append((func, args))
        return ["workflow-1"]

    monkeypatch.setattr(
        "app.logic.workflows.recovery.asyncio.to_thread", fake_to_thread
    )

    recovered = await recover_dead_workflow_executors(session, _RecoverySettings())

    assert recovered == ["workflow-1"]
    assert calls == [
        (
            recover_workflows_via_admin,
            ("http://127.0.0.1:3001", ["stale-worker"]),
        )
    ]


async def test_workflow_admin_election_promotes_when_lock_is_available() -> None:
    state = WorkflowAdminState()
    events: list[str] = []

    async def promote() -> None:
        events.append("promote")

    async def recover() -> None:
        events.append("recover")

    await workflow_admin_election_once(
        state,
        lock_acquired=True,
        promote_to_admin=promote,
        recover_once=recover,
    )

    assert state.has_admin_server is True
    assert events == ["promote", "recover"]


async def test_workflow_admin_election_retries_after_missing_lock() -> None:
    state = WorkflowAdminState()
    events: list[str] = []

    async def promote() -> None:
        events.append("promote")

    async def recover() -> None:
        events.append("recover")

    await workflow_admin_election_once(
        state,
        lock_acquired=False,
        promote_to_admin=promote,
        recover_once=recover,
    )
    await workflow_admin_election_once(
        state,
        lock_acquired=True,
        promote_to_admin=promote,
        recover_once=recover,
    )

    assert state.has_admin_server is True
    assert events == ["promote", "recover"]

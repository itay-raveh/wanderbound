import asyncio
import json
import os
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import structlog
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.core.locks import try_advisory_lock
from app.models.processing import WorkflowExecutorHeartbeat

logger = structlog.get_logger(__name__)

WORKFLOW_RECOVERY_PATH = "/dbos-workflow-recovery"


@dataclass
class WorkflowAdminState:
    has_admin_server: bool = False


class WorkflowRecoverySettings(Protocol):
    DBOS_EXECUTOR_ID: str | None
    DBOS_ADMIN_PORT: int
    DBOS_HEARTBEAT_TTL_SECONDS: float
    DBOS_RECOVERY_INTERVAL_SECONDS: float


def workflow_admin_base_url(settings: WorkflowRecoverySettings) -> str:
    return f"http://127.0.0.1:{settings.DBOS_ADMIN_PORT}"


def workflow_executor_id(settings: WorkflowRecoverySettings) -> str:
    if settings.DBOS_EXECUTOR_ID:
        return settings.DBOS_EXECUTOR_ID
    return f"{socket.gethostname()}-{os.getpid()}"


def _now() -> datetime:
    return datetime.now(UTC)


async def record_workflow_executor_heartbeat(
    session: AsyncSession, *, executor_id: str, admin_base_url: str | None
) -> None:
    row = await session.get(WorkflowExecutorHeartbeat, executor_id)
    if row is None:
        row = WorkflowExecutorHeartbeat(
            executor_id=executor_id, admin_base_url=admin_base_url or ""
        )
    row.admin_base_url = admin_base_url or ""
    row.status = "active"
    row.last_seen_at = _now()
    session.add(row)
    await session.flush()


async def list_dead_workflow_executors(
    session: AsyncSession, *, stale_after: timedelta
) -> list[str]:
    cutoff = _now() - stale_after
    rows = (
        await session.exec(
            select(WorkflowExecutorHeartbeat)
            .where(col(WorkflowExecutorHeartbeat.status) == "active")
            .where(col(WorkflowExecutorHeartbeat.last_seen_at) < cutoff)
            .order_by(col(WorkflowExecutorHeartbeat.executor_id))
        )
    ).all()
    executor_ids = [row.executor_id for row in rows]
    if executor_ids:
        await session.exec(
            update(WorkflowExecutorHeartbeat)
            .where(col(WorkflowExecutorHeartbeat.executor_id).in_(executor_ids))
            .values(status="dead")
        )
        await session.flush()
    return executor_ids


def recover_workflows_via_admin(
    admin_base_url: str, executor_ids: list[str]
) -> list[str]:
    parsed_url = urlparse(admin_base_url)
    if parsed_url.scheme not in {"http", "https"}:
        msg = "DBOS admin URL must use http or https"
        raise ValueError(msg)
    request = Request(  # noqa: S310
        f"{admin_base_url.rstrip('/')}{WORKFLOW_RECOVERY_PATH}",
        data=json.dumps(executor_ids).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310
        return list(json.loads(response.read().decode()))


async def recover_dead_workflow_executors(
    session: AsyncSession, settings: WorkflowRecoverySettings
) -> list[str]:
    admin_base_url = workflow_admin_base_url(settings)
    dead_executor_ids = await list_dead_workflow_executors(
        session, stale_after=timedelta(seconds=settings.DBOS_HEARTBEAT_TTL_SECONDS)
    )
    if not dead_executor_ids:
        return []
    return recover_workflows_via_admin(admin_base_url, dead_executor_ids)


async def workflow_heartbeat_once(
    session: AsyncSession,
    settings: WorkflowRecoverySettings,
    *,
    has_admin_server: bool,
) -> None:
    await record_workflow_executor_heartbeat(
        session,
        executor_id=workflow_executor_id(settings),
        admin_base_url=workflow_admin_base_url(settings) if has_admin_server else None,
    )


async def workflow_heartbeat_loop(
    settings: WorkflowRecoverySettings, *, has_admin_server: bool | Callable[[], bool]
) -> None:
    while True:
        try:
            async with AsyncSession(get_engine(), expire_on_commit=False) as session:
                await workflow_heartbeat_once(
                    session,
                    settings,
                    has_admin_server=(
                        has_admin_server()
                        if callable(has_admin_server)
                        else has_admin_server
                    ),
                )
                await session.commit()
        except asyncio.CancelledError:
            raise
        except OSError, SQLAlchemyError, TimeoutError, ValueError:
            logger.warning("workflow.heartbeat_failed", exc_info=True)
        await asyncio.sleep(settings.DBOS_RECOVERY_INTERVAL_SECONDS)


async def workflow_admin_election_once(
    state: WorkflowAdminState,
    *,
    lock_acquired: bool,
    promote_to_admin: Callable[[], Awaitable[None]],
    recover_once: Callable[[], Awaitable[None]],
) -> None:
    if not lock_acquired:
        return
    if not state.has_admin_server:
        await promote_to_admin()
        state.has_admin_server = True
    await recover_once()


async def workflow_admin_election_loop(
    settings: WorkflowRecoverySettings,
    state: WorkflowAdminState,
    *,
    promote_to_admin: Callable[[], Awaitable[None]],
) -> None:
    async def recover_once() -> None:
        async with AsyncSession(get_engine(), expire_on_commit=False) as session:
            recovered = await recover_dead_workflow_executors(session, settings)
            await session.commit()
            if recovered:
                logger.info(
                    "workflow.recovered", recovered_workflow_count=len(recovered)
                )

    while True:
        try:
            async with try_advisory_lock("dbos-admin") as acquired:
                if acquired:
                    await workflow_admin_election_once(
                        state,
                        lock_acquired=True,
                        promote_to_admin=promote_to_admin,
                        recover_once=recover_once,
                    )
                    while True:
                        await asyncio.sleep(settings.DBOS_RECOVERY_INTERVAL_SECONDS)
                        await workflow_admin_election_once(
                            state,
                            lock_acquired=True,
                            promote_to_admin=promote_to_admin,
                            recover_once=recover_once,
                        )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "workflow.admin_election_failed",
                error_type=type(exc).__name__,
                exc_info=True,
            )
        await asyncio.sleep(settings.DBOS_RECOVERY_INTERVAL_SECONDS)


async def workflow_recovery_loop(settings: WorkflowRecoverySettings) -> None:
    while True:
        try:
            async with AsyncSession(get_engine(), expire_on_commit=False) as session:
                recovered = await recover_dead_workflow_executors(session, settings)
                await session.commit()
                if recovered:
                    logger.info(
                        "workflow.recovered", recovered_workflow_count=len(recovered)
                    )
        except asyncio.CancelledError:
            raise
        except OSError, SQLAlchemyError, TimeoutError, ValueError:
            logger.warning("workflow.recovery_failed", exc_info=True)
        await asyncio.sleep(settings.DBOS_RECOVERY_INTERVAL_SECONDS)

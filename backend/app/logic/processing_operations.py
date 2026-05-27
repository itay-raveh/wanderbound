from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from pydantic import TypeAdapter
from sqlalchemy import func, update
from sqlmodel import col, select

from app.logic.trip_processing import ProcessingEvent
from app.models.processing import (
    ProcessingEventRow,
    ProcessingOperation,
    ProcessingOperationStatus,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

_EVENT_ADAPTER = TypeAdapter(ProcessingEvent)
_TERMINAL_STATUSES: set[ProcessingOperationStatus] = {
    "succeeded",
    "failed",
    "cancelled",
    "stale",
}
_ACTIVE_STATUSES: set[ProcessingOperationStatus] = {"queued", "running"}


def _now() -> datetime:
    return datetime.now(UTC)


def workflow_id_for_operation(operation_id: str) -> str:
    return f"processing:{operation_id}"


async def create_processing_operation(
    session: AsyncSession, *, uid: int, upload_generation: int
) -> ProcessingOperation:
    operation = ProcessingOperation(
        uid=uid,
        upload_generation=upload_generation,
        workflow_id="",
    )
    operation.workflow_id = workflow_id_for_operation(operation.operation_id)
    session.add(operation)
    await session.flush()
    return operation


async def latest_processing_operation(
    session: AsyncSession, *, uid: int
) -> ProcessingOperation | None:
    result = await session.exec(
        select(ProcessingOperation)
        .where(col(ProcessingOperation.uid) == uid)
        .order_by(col(ProcessingOperation.created_at).desc())
    )
    return result.first()


async def latest_active_processing_operation(
    session: AsyncSession, *, uid: int, upload_generation: int
) -> ProcessingOperation | None:
    result = await session.exec(
        select(ProcessingOperation)
        .where(col(ProcessingOperation.uid) == uid)
        .where(col(ProcessingOperation.upload_generation) == upload_generation)
        .where(col(ProcessingOperation.status).notin_(_TERMINAL_STATUSES))
        .order_by(col(ProcessingOperation.created_at).desc())
    )
    return result.first()


async def mark_processing_operation_running(
    session: AsyncSession,
    operation: ProcessingOperation,
    *,
    executor_id: str | None = None,
) -> None:
    now = _now()
    operation.status = "running"
    operation.started_by_executor_id = executor_id
    operation.started_at = operation.started_at or now
    operation.updated_at = now
    session.add(operation)
    await session.flush()


async def complete_processing_operation(
    session: AsyncSession,
    operation: ProcessingOperation,
    *,
    status: ProcessingOperationStatus,
    error_code: str | None = None,
) -> None:
    if status not in _TERMINAL_STATUSES:
        msg = f"{status!r} is not a terminal processing status"
        raise ValueError(msg)
    now = _now()
    operation.status = status
    operation.error_code = error_code
    operation.completed_at = now
    operation.updated_at = now
    session.add(operation)
    await session.flush()


async def processing_operation_is_active(
    session: AsyncSession, operation_id: str
) -> bool:
    status = await session.scalar(
        select(ProcessingOperation.status).where(
            col(ProcessingOperation.operation_id) == operation_id
        )
    )
    return status in _ACTIVE_STATUSES


async def processing_operation_is_active_for_update(
    session: AsyncSession, operation_id: str
) -> bool:
    result = await session.exec(
        select(ProcessingOperation)
        .where(col(ProcessingOperation.operation_id) == operation_id)
        .with_for_update()
    )
    operation = result.one_or_none()
    return operation is not None and operation.status in _ACTIVE_STATUSES


async def append_processing_event(
    session: AsyncSession,
    operation: ProcessingOperation,
    event: ProcessingEvent,
) -> ProcessingEventRow:
    next_seq = await _next_event_seq(session, operation.operation_id)
    payload = _EVENT_ADAPTER.dump_python(event, mode="json")
    row = ProcessingEventRow(
        operation_id=operation.operation_id,
        seq=next_seq,
        event_type=str(payload["type"]),
        payload=payload,
    )
    operation.updated_at = _now()
    session.add(row)
    session.add(operation)
    await session.flush()
    return row


async def read_processing_events(
    session: AsyncSession, operation_id: str, *, after_seq: int = -1
) -> list[ProcessingEvent]:
    rows = (
        await session.exec(
            select(ProcessingEventRow)
            .where(ProcessingEventRow.operation_id == operation_id)
            .where(col(ProcessingEventRow.seq) > after_seq)
            .order_by(col(ProcessingEventRow.seq))
        )
    ).all()
    return [_EVENT_ADAPTER.validate_python(row.payload) for row in rows]


async def mark_user_processing_operations_stale(
    session: AsyncSession, *, uid: int
) -> int:
    result = await session.exec(
        update(ProcessingOperation)
        .where(col(ProcessingOperation.uid) == uid)
        .where(col(ProcessingOperation.status) != "stale")
        .values(status="stale", updated_at=_now())
    )
    await session.flush()
    return int(result.rowcount or 0)


async def _next_event_seq(session: AsyncSession, operation_id: str) -> int:
    max_seq = await session.exec(
        select(func.max(ProcessingEventRow.seq)).where(
            col(ProcessingEventRow.operation_id) == operation_id
        )
    )
    value = cast("int | None", max_seq.one())
    return (-1 if value is None else value) + 1

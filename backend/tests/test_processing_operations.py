from typing import TYPE_CHECKING

from app.logic.processing_operations import (
    append_processing_event,
    complete_processing_operation,
    create_processing_operation,
    latest_active_processing_operation,
    latest_processing_operation,
    mark_processing_operation_running,
    mark_user_processing_operations_stale,
    processing_operation_is_active,
    read_processing_events,
)
from app.logic.trip_processing import PhaseUpdate, TripStart

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


async def test_create_operation_uses_app_owned_workflow_id(
    session: AsyncSession,
) -> None:
    operation = await create_processing_operation(session, uid=42, upload_generation=3)

    assert operation.uid == 42
    assert operation.upload_generation == 3
    assert operation.status == "queued"
    assert operation.workflow_id == f"processing:{operation.operation_id}"
    assert operation.started_at is None
    assert operation.completed_at is None


async def test_latest_active_operation_ignores_terminal_and_stale_rows(
    session: AsyncSession,
) -> None:
    first = await create_processing_operation(session, uid=42, upload_generation=3)
    first.status = "stale"
    session.add(first)
    second = await create_processing_operation(session, uid=42, upload_generation=3)
    done = await create_processing_operation(session, uid=42, upload_generation=3)
    done.status = "succeeded"
    other_generation = await create_processing_operation(
        session, uid=42, upload_generation=4
    )
    session.add_all([done, other_generation])
    await session.flush()

    assert (
        await latest_active_processing_operation(session, uid=42, upload_generation=3)
        == second
    )


async def test_persisted_events_replay_in_sequence(session: AsyncSession) -> None:
    operation = await create_processing_operation(session, uid=42, upload_generation=3)

    await append_processing_event(session, operation, TripStart(trip_index=0))
    await append_processing_event(
        session,
        operation,
        PhaseUpdate(phase="weather", done=1, total=2),
    )

    events = await read_processing_events(session, operation.operation_id)

    assert events == [
        TripStart(trip_index=0),
        PhaseUpdate(phase="weather", done=1, total=2),
    ]


async def test_mark_user_processing_operations_stale_updates_all_non_stale_rows(
    session: AsyncSession,
) -> None:
    active = await create_processing_operation(session, uid=42, upload_generation=3)
    failed = await create_processing_operation(session, uid=42, upload_generation=2)
    failed.status = "failed"
    other_user = await create_processing_operation(session, uid=7, upload_generation=1)
    session.add_all([failed, other_user])
    await session.flush()

    stale_count = await mark_user_processing_operations_stale(session, uid=42)

    assert stale_count == 2
    assert active.status == "stale"
    assert failed.status == "stale"
    assert other_user.status == "queued"


async def test_latest_processing_operation_includes_terminal_rows(
    session: AsyncSession,
) -> None:
    first = await create_processing_operation(session, uid=42, upload_generation=3)
    await complete_processing_operation(session, first, status="succeeded")
    second = await create_processing_operation(session, uid=42, upload_generation=4)

    assert await latest_processing_operation(session, uid=42) == second


async def test_status_helpers_track_running_terminal_and_active(
    session: AsyncSession,
) -> None:
    operation = await create_processing_operation(session, uid=42, upload_generation=3)

    assert await processing_operation_is_active(session, operation.operation_id) is True

    await mark_processing_operation_running(session, operation, executor_id="worker-1")

    assert operation.status == "running"
    assert operation.started_by_executor_id == "worker-1"
    assert operation.started_at is not None
    assert operation.completed_at is None
    assert await processing_operation_is_active(session, operation.operation_id) is True

    await complete_processing_operation(session, operation, status="succeeded")

    assert operation.status == "succeeded"
    assert operation.completed_at is not None
    active = await processing_operation_is_active(session, operation.operation_id)
    assert active is False


async def test_mark_running_does_not_revive_stale_operation(
    session: AsyncSession,
) -> None:
    operation = await create_processing_operation(session, uid=42, upload_generation=3)
    operation.status = "stale"
    session.add(operation)
    await session.flush()

    updated = await mark_processing_operation_running(session, operation)

    assert updated is False
    assert operation.status == "stale"


async def test_complete_operation_does_not_overwrite_stale_operation(
    session: AsyncSession,
) -> None:
    operation = await create_processing_operation(session, uid=42, upload_generation=3)
    operation.status = "stale"
    session.add(operation)
    await session.flush()

    updated = await complete_processing_operation(
        session, operation, status="succeeded"
    )

    assert updated is False
    assert operation.status == "stale"

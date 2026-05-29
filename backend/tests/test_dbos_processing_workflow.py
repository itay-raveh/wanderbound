from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from app.logic.processing_operations import (
    append_processing_event,
    create_processing_operation,
    read_processing_events,
)
from app.logic.trip_processing import ErrorData, PhaseUpdate, ProcessingEvent, TripStart
from app.logic.workflows.processing import (
    ProcessingWorkflowPayload,
    processing_upload_workflow,
    processing_workflow_payload,
    run_and_persist_processing_events,
    run_processing_workflow_payload,
    start_processing_workflow,
)
from app.models.processing import ProcessingOperation
from app.models.user import User

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


def _operation() -> ProcessingOperation:
    return ProcessingOperation(
        operation_id="op_123",
        uid=42,
        upload_generation=7,
        workflow_id="processing:op_123",
    )


def _user() -> User:
    user = AsyncMock(spec=User)
    user.id = 42
    user.album_ids = ["trip-b", "trip-a"]
    user.trips_folder = "/data/users/42/trips"
    return user


def test_processing_workflow_payload_is_json_serializable() -> None:
    payload = processing_workflow_payload(_operation(), _user())

    assert payload == {
        "operation_id": "op_123",
        "uid": 42,
        "upload_generation": 7,
        "trips_folder": "/data/users/42/trips",
        "album_ids": ["trip-b", "trip-a"],
    }
    assert ProcessingWorkflowPayload.model_validate(payload).album_ids == (
        "trip-b",
        "trip-a",
    )


def test_start_processing_workflow_uses_operation_workflow_id(
    monkeypatch: Any,
) -> None:
    calls: list[tuple[object, dict[str, Any]]] = []
    workflow_ids: list[str] = []
    handle = object()

    class FakeSetWorkflowID:
        def __init__(self, workflow_id: str) -> None:
            self.workflow_id = workflow_id

        def __enter__(self) -> None:
            workflow_ids.append(self.workflow_id)

        def __exit__(self, *args: object) -> None:
            return None

    def fake_start_workflow(func: object, payload: dict[str, Any]) -> object:
        calls.append((func, payload))
        return handle

    monkeypatch.setattr(
        "app.logic.workflows.processing.SetWorkflowID", FakeSetWorkflowID
    )
    monkeypatch.setattr(
        "app.logic.workflows.processing.DBOS.start_workflow",
        fake_start_workflow,
    )

    result = start_processing_workflow(_operation(), _user())

    assert result is handle
    assert workflow_ids == ["processing:op_123"]
    assert calls == [
        (
            processing_upload_workflow,
            {
                "operation_id": "op_123",
                "uid": 42,
                "upload_generation": 7,
                "trips_folder": "/data/users/42/trips",
                "album_ids": ["trip-b", "trip-a"],
            },
        )
    ]


async def test_run_processing_workflow_payload_persists_events_and_succeeds(
    session: AsyncSession,
) -> None:
    user = User(
        id=42,
        google_sub="google-42",
        first_name="Test",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
        album_ids=["trip-1", "trip-2"],
    )
    session.add(user)
    await session.flush()
    operation = await create_processing_operation(session, uid=42, upload_generation=1)
    await session.commit()

    async def fake_run_processing(
        _http: object, _user: User, **_kwargs: object
    ) -> AsyncIterator[ProcessingEvent]:
        yield TripStart(trip_index=0)
        yield PhaseUpdate(phase="layouts", done=1, total=1)

    http = MagicMock()
    with (
        patch("app.logic.workflows.processing.run_processing", fake_run_processing),
        patch(
            "app.logic.workflows.processing.schedule_album_route_enrichment"
        ) as schedule,
    ):
        result = await run_processing_workflow_payload(
            processing_workflow_payload(operation, user),
            http,
            session,
        )

    await session.refresh(operation)
    events = await read_processing_events(session, operation.operation_id)

    assert result == {"operation_id": operation.operation_id, "status": "succeeded"}
    assert operation.status == "succeeded"
    assert events == [
        TripStart(trip_index=0),
        PhaseUpdate(phase="layouts", done=1, total=1),
    ]
    assert [call.args for call in schedule.call_args_list] == [
        (http, 42, "trip-1"),
        (http, 42, "trip-2"),
    ]


async def test_run_processing_workflow_payload_marks_failed_on_error_event(
    session: AsyncSession,
) -> None:
    user = User(
        id=42,
        google_sub="google-42",
        first_name="Test",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
        album_ids=["trip-1"],
    )
    session.add(user)
    await session.flush()
    operation = await create_processing_operation(session, uid=42, upload_generation=1)
    await session.commit()

    async def fake_run_processing(
        _http: object, _user: User, **_kwargs: object
    ) -> AsyncIterator[ProcessingEvent]:
        yield ErrorData()

    with (
        patch("app.logic.workflows.processing.run_processing", fake_run_processing),
        patch(
            "app.logic.workflows.processing.schedule_album_route_enrichment"
        ) as schedule,
    ):
        result = await run_processing_workflow_payload(
            processing_workflow_payload(operation, user),
            MagicMock(),
            session,
        )

    await session.refresh(operation)

    assert result == {"operation_id": operation.operation_id, "status": "failed"}
    assert operation.status == "failed"
    schedule.assert_not_called()


async def test_run_processing_workflow_payload_marks_failed_when_processing_raises(
    session: AsyncSession,
) -> None:
    user = User(
        id=42,
        google_sub="google-42",
        first_name="Test",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
        album_ids=["trip-1"],
    )
    session.add(user)
    await session.flush()
    operation = await create_processing_operation(session, uid=42, upload_generation=1)
    await session.commit()

    async def fake_run_processing(
        _http: object, _user: User, **_kwargs: object
    ) -> AsyncIterator[ProcessingEvent]:
        yield TripStart(trip_index=0)
        msg = "boom"
        raise RuntimeError(msg)

    with (
        patch("app.logic.workflows.processing.run_processing", fake_run_processing),
        patch(
            "app.logic.workflows.processing.schedule_album_route_enrichment"
        ) as schedule,
    ):
        result = await run_processing_workflow_payload(
            processing_workflow_payload(operation, user),
            MagicMock(),
            session,
        )

    await session.refresh(operation)
    events = await read_processing_events(session, operation.operation_id)

    assert result == {"operation_id": operation.operation_id, "status": "failed"}
    assert operation.status == "failed"
    assert events == [TripStart(trip_index=0), ErrorData()]
    schedule.assert_not_called()


async def test_recovered_failed_processing_run_does_not_duplicate_error_event(
    session: AsyncSession,
) -> None:
    user = User(
        id=42,
        google_sub="google-42",
        first_name="Test",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
        album_ids=["trip-1"],
    )
    session.add(user)
    await session.flush()
    operation = await create_processing_operation(session, uid=42, upload_generation=1)
    operation.status = "running"
    session.add(operation)
    await session.flush()
    await append_processing_event(session, operation, TripStart(trip_index=0))
    await append_processing_event(session, operation, ErrorData())
    await session.commit()

    async def fake_run_processing(
        _http: object, _user: User, **_kwargs: object
    ) -> AsyncIterator[ProcessingEvent]:
        yield TripStart(trip_index=0)
        msg = "boom"
        raise RuntimeError(msg)

    with patch("app.logic.workflows.processing.run_processing", fake_run_processing):
        await run_processing_workflow_payload(
            processing_workflow_payload(operation, user),
            MagicMock(),
            session,
        )

    events = await read_processing_events(session, operation.operation_id)

    assert events == [TripStart(trip_index=0), ErrorData()]


async def test_run_processing_workflow_payload_exits_when_user_was_deleted(
    session: AsyncSession,
) -> None:
    result = await run_processing_workflow_payload(
        {
            "operation_id": "deleted-operation",
            "uid": 42,
            "upload_generation": 1,
            "trips_folder": "/deleted",
            "album_ids": [],
        },
        MagicMock(),
        session,
    )

    assert result == {"operation_id": "deleted-operation", "status": "cancelled"}


async def test_run_processing_workflow_payload_preserves_stale_operation(
    session: AsyncSession,
) -> None:
    user = User(
        id=42,
        google_sub="google-42",
        first_name="Test",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
        album_ids=["trip-1"],
    )
    session.add(user)
    await session.flush()
    operation = await create_processing_operation(session, uid=42, upload_generation=1)
    await session.commit()

    async def fake_run_processing(
        _http: object, _user: User, **kwargs: object
    ) -> AsyncIterator[ProcessingEvent]:
        operation.status = "stale"
        session.add(operation)
        await session.commit()
        should_continue = cast(
            "Callable[[], Awaitable[bool]]", kwargs["should_continue"]
        )
        assert await should_continue() is False
        yield ErrorData()

    with patch("app.logic.workflows.processing.run_processing", fake_run_processing):
        result = await run_processing_workflow_payload(
            processing_workflow_payload(operation, user),
            MagicMock(),
            session,
        )

    await session.refresh(operation)
    assert result == {"operation_id": operation.operation_id, "status": "stale"}
    assert operation.status == "stale"


async def test_run_processing_workflow_payload_exits_when_operation_already_stale(
    session: AsyncSession,
) -> None:
    user = User(
        id=42,
        google_sub="google-42",
        first_name="Test",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
        album_ids=["trip-1"],
    )
    session.add(user)
    await session.flush()
    operation = await create_processing_operation(session, uid=42, upload_generation=1)
    operation.status = "stale"
    session.add(operation)
    await session.commit()

    run_calls = 0

    async def fake_run_processing(
        _http: object, _user: User, **_kwargs: object
    ) -> AsyncIterator[ProcessingEvent]:
        nonlocal run_calls
        run_calls += 1
        yield ErrorData()

    with patch("app.logic.workflows.processing.run_processing", fake_run_processing):
        result = await run_processing_workflow_payload(
            processing_workflow_payload(operation, user),
            MagicMock(),
            session,
        )

    await session.refresh(operation)
    assert result == {"operation_id": operation.operation_id, "status": "stale"}
    assert operation.status == "stale"
    assert run_calls == 0


async def test_recovered_processing_run_skips_nondeterministic_persisted_events(
    session: AsyncSession,
) -> None:
    user = User(
        id=42,
        google_sub="google-42",
        first_name="Test",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
        album_ids=["trip-1"],
    )
    session.add(user)
    await session.flush()
    operation = await create_processing_operation(session, uid=42, upload_generation=1)
    await session.commit()

    run_count = 0

    async def fake_run_processing(
        _http: object, _user: User, **_kwargs: object
    ) -> AsyncIterator[ProcessingEvent]:
        nonlocal run_count
        run_count += 1
        yield TripStart(trip_index=0)
        if run_count == 1:
            yield PhaseUpdate(phase="weather", done=1, total=2)
            yield PhaseUpdate(phase="elevations", done=1, total=2)
        else:
            yield PhaseUpdate(phase="elevations", done=1, total=2)
            yield PhaseUpdate(phase="weather", done=1, total=2)
            yield PhaseUpdate(phase="layouts", done=1, total=1)

    with patch("app.logic.workflows.processing.run_processing", fake_run_processing):
        await run_and_persist_processing_events(MagicMock(), user, operation, session)
        await run_and_persist_processing_events(MagicMock(), user, operation, session)

    events = await read_processing_events(session, operation.operation_id)

    assert events == [
        TripStart(trip_index=0),
        PhaseUpdate(phase="weather", done=1, total=2),
        PhaseUpdate(phase="elevations", done=1, total=2),
        PhaseUpdate(phase="layouts", done=1, total=1),
    ]


async def test_processing_save_guard_marks_operation_succeeded_in_save_transaction(
    session: AsyncSession,
) -> None:
    user = User(
        id=42,
        google_sub="google-42",
        first_name="Test",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
        album_ids=["trip-1"],
    )
    session.add(user)
    await session.flush()
    operation = await create_processing_operation(session, uid=42, upload_generation=1)
    await session.commit()

    async def fake_run_processing(
        _http: object, _user: User, **kwargs: object
    ) -> AsyncIterator[ProcessingEvent]:
        yield TripStart(trip_index=0)
        save_guard = cast(
            "Callable[[AsyncSession], Awaitable[bool]]", kwargs["save_guard"]
        )
        assert await save_guard(session) is True
        await session.commit()

    with patch("app.logic.workflows.processing.run_processing", fake_run_processing):
        saw_error = await run_and_persist_processing_events(
            MagicMock(), user, operation, session
        )

    await session.refresh(operation)

    assert saw_error is False
    assert operation.status == "succeeded"

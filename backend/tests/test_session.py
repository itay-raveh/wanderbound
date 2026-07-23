import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.http_clients import HttpClients
from app.logic.processing_operations import (
    append_processing_event,
    complete_processing_operation,
    create_processing_operation,
    latest_processing_operation,
    mark_processing_operation_running,
    mark_user_processing_operations_stale,
)
from app.logic.session import (
    ProcessingSession,
    _operation_for_process_request,
    _sessions,
    process_stream,
)
from app.logic.trip_processing import (
    ErrorData,
    PhaseUpdate,
    ProcessingEvent,
    TripStart,
)
from app.models.user import User
from tests.factories import collect_async

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

_MOCK_HTTP = MagicMock(spec=HttpClients)


def _mock_user(uid: int = 1) -> User:
    user = AsyncMock(spec=User)
    user.id = uid
    user.album_ids = ["trip-1", "trip-2"]
    user.trips_folder = AsyncMock()
    return user


def _processing_events(
    *events: ProcessingEvent,
) -> Callable[[HttpClients, User], AsyncIterator[ProcessingEvent]]:
    async def fake_processing(
        _http: HttpClients, _user: User
    ) -> AsyncIterator[ProcessingEvent]:
        for event in events:
            yield event

    return fake_processing


def _gated_processing(
    gate: asyncio.Event,
    *,
    before: list[ProcessingEvent],
    after: list[ProcessingEvent],
) -> Callable[[HttpClients, User], AsyncIterator[ProcessingEvent]]:
    async def fake_processing(
        _http: HttpClients, _user: User
    ) -> AsyncIterator[ProcessingEvent]:
        for event in before:
            yield event
        await gate.wait()
        for event in after:
            yield event

    return fake_processing


def _scheduled_album_calls(uid: int) -> list[tuple[HttpClients, int, str]]:
    return [
        (_MOCK_HTTP, uid, "trip-1"),
        (_MOCK_HTTP, uid, "trip-2"),
    ]


class TestProcessingSession:
    async def test_replay_past_events_on_late_subscribe(self) -> None:
        events = [
            TripStart(trip_index=0),
            PhaseUpdate(phase="layouts", done=5, total=5),
        ]

        with (
            patch("app.logic.session.run_processing", _processing_events(*events)),
            patch("app.logic.session.schedule_album_route_enrichment"),
        ):
            session = ProcessingSession(_MOCK_HTTP, _mock_user())
            await session._task
            assert session.is_done
            result = await collect_async(session.subscribe())

        assert result == events

    async def test_enqueues_route_enrichment_after_successful_processing(
        self,
    ) -> None:
        user = _mock_user(uid=42)
        with (
            patch(
                "app.logic.session.run_processing",
                _processing_events(PhaseUpdate(phase="layouts", done=1, total=1)),
            ),
            patch("app.logic.session.schedule_album_route_enrichment") as schedule,
        ):
            session = ProcessingSession(_MOCK_HTTP, user)
            await session._task

        calls = [call.args for call in schedule.call_args_list]
        assert calls == _scheduled_album_calls(42)

    async def test_does_not_enqueue_route_enrichment_after_processing_error(
        self,
    ) -> None:
        with (
            patch("app.logic.session.run_processing", _processing_events(ErrorData())),
            patch("app.logic.session.schedule_album_route_enrichment") as schedule,
        ):
            session = ProcessingSession(_MOCK_HTTP, _mock_user())
            await session._task

        schedule.assert_not_called()


class TestProcessStream:
    @pytest.fixture(autouse=True)
    def _clean_sessions(self) -> Iterator[None]:
        with patch("app.logic.session.schedule_album_route_enrichment"):
            _sessions.clear()
            yield
            _sessions.clear()

    async def test_reconnect_to_running_session(self) -> None:
        gate = asyncio.Event()
        events_before_gate = [TripStart(trip_index=0)]
        events_after_gate = [PhaseUpdate(phase="elevations", done=1, total=5)]

        user = _mock_user(uid=99)
        with patch(
            "app.logic.session.run_processing",
            _gated_processing(gate, before=events_before_gate, after=events_after_gate),
        ):
            session = ProcessingSession(_MOCK_HTTP, user)
            _sessions[user.id] = session

            await session._notify.wait()

            collected: list[ProcessingEvent] = []
            async for event in process_stream(_MOCK_HTTP, user):
                collected.append(event)
                if isinstance(event, TripStart):
                    gate.set()

            assert collected == events_before_gate + events_after_gate

    async def test_replays_completed_session(self) -> None:
        call_count = 0

        async def fake_processing(
            _http: HttpClients, _user: User
        ) -> AsyncIterator[ProcessingEvent]:
            nonlocal call_count
            call_count += 1
            yield TripStart(trip_index=0)

        user = _mock_user(uid=7)
        with patch("app.logic.session.run_processing", fake_processing):
            first = await collect_async(process_stream(_MOCK_HTTP, user))
            second = await collect_async(process_stream(_MOCK_HTTP, user))

        assert call_count == 1  # Only one processing run
        assert first == second  # Replayed same events

    async def test_failed_session_retries_with_fresh_run(self) -> None:
        call_count = 0

        async def fake_processing(
            _http: HttpClients, _user: User
        ) -> AsyncIterator[ProcessingEvent]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield ErrorData()
            else:
                yield TripStart(trip_index=0)

        user = _mock_user(uid=11)
        with patch("app.logic.session.run_processing", fake_processing):
            first = await collect_async(process_stream(_MOCK_HTTP, user))
            second = await collect_async(process_stream(_MOCK_HTTP, user))

        assert call_count == 2  # Fresh run after error, not replay
        assert first == [ErrorData()]
        assert second == [TripStart(trip_index=0)]

    async def test_concurrent_same_user_shares_session(self) -> None:
        gate = asyncio.Event()
        call_count = 0

        async def fake_processing(
            _http: HttpClients, _user: User
        ) -> AsyncIterator[ProcessingEvent]:
            nonlocal call_count
            call_count += 1
            yield TripStart(trip_index=0)
            await gate.wait()

        user = _mock_user(uid=5)
        with patch("app.logic.session.run_processing", fake_processing):
            session = ProcessingSession(_MOCK_HTTP, user)
            _sessions[user.id] = session

            await session._notify.wait()

            async def second_stream() -> list[ProcessingEvent]:
                return await collect_async(process_stream(_MOCK_HTTP, user))

            task = asyncio.create_task(second_stream())
            await asyncio.sleep(0.05)
            gate.set()

            result = await task

        assert call_count == 1
        assert result[0] == TripStart(trip_index=0)

    async def test_route_enrichment_survives_subscriber_disconnect(self) -> None:
        gate = asyncio.Event()

        user = _mock_user(uid=22)
        with (
            patch(
                "app.logic.session.run_processing",
                _gated_processing(
                    gate,
                    before=[TripStart(trip_index=0)],
                    after=[PhaseUpdate(phase="layouts", done=1, total=1)],
                ),
            ),
            patch("app.logic.session.schedule_album_route_enrichment") as schedule,
        ):
            stream = process_stream(_MOCK_HTTP, user)
            first = await anext(stream)
            await stream.aclose()

            gate.set()
            session = _sessions[user.id]
            await session._task

        assert first == TripStart(trip_index=0)
        calls = [call.args for call in schedule.call_args_list]
        assert calls == _scheduled_album_calls(22)


class TestPersistedProcessStream:
    @pytest.fixture(autouse=True)
    def _clean_sessions(self) -> Iterator[None]:
        _sessions.clear()
        yield
        _sessions.clear()

    async def test_completed_processing_replays_from_database_after_memory_eviction(
        self, session: AsyncSession
    ) -> None:
        starts: list[str] = []

        def fake_start_processing_workflow(operation: object, _user: User) -> object:
            starts.append(operation.workflow_id)
            return object()

        async def finish_operation() -> None:
            await asyncio.sleep(0.01)
            operation = await latest_processing_operation(session, uid=123)
            assert operation is not None
            await mark_processing_operation_running(session, operation)
            await append_processing_event(session, operation, TripStart(trip_index=0))
            await append_processing_event(
                session, operation, PhaseUpdate(phase="layouts", done=1, total=1)
            )
            await complete_processing_operation(session, operation, status="succeeded")
            await session.commit()

        user = _mock_user(uid=123)
        with patch(
            "app.logic.session.start_processing_workflow",
            fake_start_processing_workflow,
        ):
            finisher = asyncio.create_task(finish_operation())
            first = await collect_async(process_stream(_MOCK_HTTP, user, session))
            await finisher
            _sessions.clear()
            second = await collect_async(process_stream(_MOCK_HTTP, user, session))

        operation = await latest_processing_operation(session, uid=123)
        assert operation is not None
        assert operation.status == "succeeded"
        assert starts == ["processing:" + operation.operation_id]
        assert (
            first
            == second
            == [
                TripStart(trip_index=0),
                PhaseUpdate(phase="layouts", done=1, total=1),
            ]
        )

    async def test_running_operation_without_local_session_polls_database_events(
        self, session: AsyncSession
    ) -> None:
        user = _mock_user(uid=321)
        operation = await create_processing_operation(
            session, uid=321, upload_generation=1
        )
        await mark_processing_operation_running(session, operation)
        await append_processing_event(session, operation, TripStart(trip_index=0))
        await session.commit()

        async def fake_processing(
            _http: HttpClients, _user: User
        ) -> AsyncIterator[ProcessingEvent]:
            if _user.uid == -1:
                yield TripStart(trip_index=99)
            msg = "running operation should not start duplicate processing"
            raise AssertionError(msg)

        async def finish_operation() -> None:
            await asyncio.sleep(0.01)
            await append_processing_event(
                session,
                operation,
                PhaseUpdate(phase="layouts", done=1, total=1),
            )
            await complete_processing_operation(session, operation, status="succeeded")
            await session.commit()

        with patch("app.logic.session.run_processing", fake_processing):
            finisher = asyncio.create_task(finish_operation())
            events = await collect_async(process_stream(_MOCK_HTTP, user, session))
            await finisher

        assert events == [
            TripStart(trip_index=0),
            PhaseUpdate(phase="layouts", done=1, total=1),
        ]

    async def test_queued_operation_starts_dbos_and_polls_database_events(
        self, session: AsyncSession
    ) -> None:
        user = _mock_user(uid=654)
        workflow_started = asyncio.Event()

        async def fake_processing(
            _http: HttpClients, _user: User
        ) -> AsyncIterator[ProcessingEvent]:
            if _user.uid == -1:
                yield TripStart(trip_index=99)
            msg = "queued operation should start DBOS, not local processing"
            raise AssertionError(msg)

        async def finish_operation() -> None:
            await workflow_started.wait()
            operation = await latest_processing_operation(session, uid=654)
            assert operation is not None
            await mark_processing_operation_running(session, operation)
            await append_processing_event(session, operation, TripStart(trip_index=0))
            await append_processing_event(
                session,
                operation,
                PhaseUpdate(phase="layouts", done=1, total=1),
            )
            await complete_processing_operation(session, operation, status="succeeded")
            await session.commit()

        starts: list[str] = []

        def fake_start_processing_workflow(operation: object, _user: User) -> object:
            starts.append(operation.workflow_id)
            workflow_started.set()
            return object()

        with (
            patch("app.logic.session.run_processing", fake_processing),
            patch(
                "app.logic.session.start_processing_workflow",
                fake_start_processing_workflow,
                create=True,
            ),
        ):
            finisher = asyncio.create_task(finish_operation())
            events = await collect_async(process_stream(_MOCK_HTTP, user, session))
            await finisher

        operation = await latest_processing_operation(session, uid=654)
        assert operation is not None
        assert starts == ["processing:" + operation.operation_id]
        assert events == [
            TripStart(trip_index=0),
            PhaseUpdate(phase="layouts", done=1, total=1),
        ]

    async def test_reupload_after_success_creates_new_operation(
        self, session: AsyncSession
    ) -> None:
        user = User(
            id=987,
            google_sub="google-987",
            first_name="Test",
            locale="en-US",
            unit_is_km=True,
            temperature_is_celsius=True,
            album_ids=["trip-1"],
        )
        session.add(user)
        await session.flush()
        old = await create_processing_operation(session, uid=987, upload_generation=1)
        await append_processing_event(session, old, TripStart(trip_index=0))
        await complete_processing_operation(session, old, status="succeeded")
        await mark_user_processing_operations_stale(session, uid=987)

        new = await _operation_for_process_request(session, user)

        assert new.operation_id != old.operation_id
        assert new.upload_generation == 2
        assert new.status == "queued"

    async def test_process_request_locks_user_before_operation_decision(
        self, session: AsyncSession
    ) -> None:
        user = _mock_user(uid=222)

        with patch(
            "app.logic.session.lock_user_for_processing_request",
            new_callable=AsyncMock,
            create=True,
        ) as lock_user:
            await _operation_for_process_request(session, user)

        lock_user.assert_awaited_once_with(session, uid=222)

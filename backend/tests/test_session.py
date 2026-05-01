import asyncio
from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.http_clients import HttpClients
from app.logic.session import (
    ProcessingSession,
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

_MOCK_HTTP = MagicMock(spec=HttpClients)


def _mock_user(uid: int = 1) -> User:
    user = AsyncMock(spec=User)
    user.id = uid
    user.album_ids = ["trip-1", "trip-2"]
    user.trips_folder = AsyncMock()
    return user


class TestProcessingSession:
    async def test_replay_past_events_on_late_subscribe(self) -> None:
        events = [
            TripStart(trip_index=0),
            PhaseUpdate(phase="layouts", done=5, total=5),
        ]

        async def fake_processing(
            _http: HttpClients, _user: User
        ) -> AsyncIterator[ProcessingEvent]:
            for e in events:
                yield e

        with patch("app.logic.session.run_processing", fake_processing):
            session = ProcessingSession(_MOCK_HTTP, _mock_user())
            # Wait for processing to finish
            await session._task
            assert session.is_done
            # Late subscriber still gets everything
            result = await collect_async(session.subscribe())

        assert result == events

    async def test_enqueues_route_enrichment_after_successful_processing(
        self,
    ) -> None:
        async def fake_processing(
            _http: HttpClients, _user: User
        ) -> AsyncIterator[ProcessingEvent]:
            yield PhaseUpdate(phase="layouts", done=1, total=1)

        user = _mock_user(uid=42)
        with (
            patch("app.logic.session.run_processing", fake_processing),
            patch("app.logic.session.schedule_album_route_enrichment") as schedule,
        ):
            session = ProcessingSession(_MOCK_HTTP, user)
            await session._task

        assert [call.args for call in schedule.call_args_list] == [
            (_MOCK_HTTP, 42, "trip-1"),
            (_MOCK_HTTP, 42, "trip-2"),
        ]

    async def test_does_not_enqueue_route_enrichment_after_processing_error(
        self,
    ) -> None:
        async def fake_processing(
            _http: HttpClients, _user: User
        ) -> AsyncIterator[ProcessingEvent]:
            yield ErrorData()

        with (
            patch("app.logic.session.run_processing", fake_processing),
            patch("app.logic.session.schedule_album_route_enrichment") as schedule,
        ):
            session = ProcessingSession(_MOCK_HTTP, _mock_user())
            await session._task

        schedule.assert_not_called()


class TestProcessStream:
    @pytest.fixture(autouse=True)
    def _clean_sessions(self) -> Iterator[None]:
        _sessions.clear()
        yield
        _sessions.clear()

    async def test_reconnect_to_running_session(self) -> None:
        gate = asyncio.Event()
        events_before_gate = [TripStart(trip_index=0)]
        events_after_gate = [PhaseUpdate(phase="elevations", done=1, total=5)]

        async def fake_processing(
            _http: HttpClients, _user: User
        ) -> AsyncIterator[ProcessingEvent]:
            for e in events_before_gate:
                yield e
            await gate.wait()
            for e in events_after_gate:
                yield e

        user = _mock_user(uid=99)
        with patch("app.logic.session.run_processing", fake_processing):
            # Start first subscriber - it will block at gate
            session = ProcessingSession(_MOCK_HTTP, user)
            _sessions[user.id] = session

            # Wait for first event to be produced
            await session._notify.wait()

            # Second subscriber (reconnect) should get replayed events
            collected: list[ProcessingEvent] = []
            async for event in process_stream(_MOCK_HTTP, user):
                collected.append(event)
                if isinstance(event, TripStart):
                    # After replay, release the gate
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
            # Start first stream
            session = ProcessingSession(_MOCK_HTTP, user)
            _sessions[user.id] = session

            await session._notify.wait()

            # Start second stream (should reconnect, not create new)
            async def second_stream() -> list[ProcessingEvent]:
                return await collect_async(process_stream(_MOCK_HTTP, user))

            task = asyncio.create_task(second_stream())
            await asyncio.sleep(0.05)
            gate.set()

            result = await task

        assert call_count == 1  # Only one processing run
        assert result[0] == TripStart(trip_index=0)

    async def test_route_enrichment_survives_subscriber_disconnect(self) -> None:
        gate = asyncio.Event()

        async def fake_processing(
            _http: HttpClients, _user: User
        ) -> AsyncIterator[ProcessingEvent]:
            yield TripStart(trip_index=0)
            await gate.wait()
            yield PhaseUpdate(phase="layouts", done=1, total=1)

        user = _mock_user(uid=22)
        with (
            patch("app.logic.session.run_processing", fake_processing),
            patch("app.logic.session.schedule_album_route_enrichment") as schedule,
        ):
            stream = process_stream(_MOCK_HTTP, user)
            first = await anext(stream)
            await stream.aclose()

            gate.set()
            session = _sessions[user.id]
            await session._task

        assert first == TripStart(trip_index=0)
        assert [call.args for call in schedule.call_args_list] == [
            (_MOCK_HTTP, 22, "trip-1"),
            (_MOCK_HTTP, 22, "trip-2"),
        ]

import asyncio
from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, patch

import pytest

from app.logic.processing import (
    PhaseUpdate,
    ProcessingEvent,
    TripStart,
)
from app.logic.session import (
    ProcessingSession,
    _sessions,
    process_stream,
)
from app.models.user import User
from tests.factories import collect_async


def _mock_user(uid: int = 1) -> User:
    user = AsyncMock(spec=User)
    user.id = uid
    user.trips_folder = AsyncMock()
    return user


class TestProcessingSession:
    async def test_replay_past_events_on_late_subscribe(self) -> None:
        events = [
            TripStart(trip_index=0),
            PhaseUpdate(phase="layouts", done=5, total=5),
        ]

        async def fake_processing(_user: User) -> AsyncIterator[ProcessingEvent]:
            for e in events:
                yield e

        with patch("app.logic.session.run_processing", fake_processing):
            session = ProcessingSession(_mock_user())
            # Wait for processing to finish
            await session._task
            assert session.is_done
            # Late subscriber still gets everything
            result = await collect_async(session.subscribe())

        assert result == events


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

        async def fake_processing(_user: User) -> AsyncIterator[ProcessingEvent]:
            for e in events_before_gate:
                yield e
            await gate.wait()
            for e in events_after_gate:
                yield e

        user = _mock_user(uid=99)
        with patch("app.logic.session.run_processing", fake_processing):
            # Start first subscriber - it will block at gate
            session = ProcessingSession(user)
            _sessions[user.id] = session

            # Wait for first event to be produced
            await session._notify.wait()

            # Second subscriber (reconnect) should get replayed events
            collected: list[ProcessingEvent] = []
            async for event in process_stream(user):
                collected.append(event)
                if isinstance(event, TripStart):
                    # After replay, release the gate
                    gate.set()

            assert collected == events_before_gate + events_after_gate

    async def test_replays_completed_session(self) -> None:
        call_count = 0

        async def fake_processing(_user: User) -> AsyncIterator[ProcessingEvent]:
            nonlocal call_count
            call_count += 1
            yield TripStart(trip_index=0)

        user = _mock_user(uid=7)
        with patch("app.logic.session.run_processing", fake_processing):
            first = await collect_async(process_stream(user))
            second = await collect_async(process_stream(user))

        assert call_count == 1  # Only one processing run
        assert first == second  # Replayed same events

    async def test_concurrent_same_user_shares_session(self) -> None:
        gate = asyncio.Event()
        call_count = 0

        async def fake_processing(_user: User) -> AsyncIterator[ProcessingEvent]:
            nonlocal call_count
            call_count += 1
            yield TripStart(trip_index=0)
            await gate.wait()

        user = _mock_user(uid=5)
        with patch("app.logic.session.run_processing", fake_processing):
            # Start first stream
            session = ProcessingSession(user)
            _sessions[user.id] = session

            await session._notify.wait()

            # Start second stream (should reconnect, not create new)
            async def second_stream() -> list[ProcessingEvent]:
                return await collect_async(process_stream(user))

            task = asyncio.create_task(second_stream())
            await asyncio.sleep(0.05)
            gate.set()

            result = await task

        assert call_count == 1  # Only one processing run
        assert result[0] == TripStart(trip_index=0)

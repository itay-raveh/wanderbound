"""Tests for ProcessingSession: per-user lock, reconnection, and event replay."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, patch

import pytest

from app.logic.processing import (
    ErrorData,
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
from tests.conftest import collect_async

# Helpers


def _mock_user(uid: int = 1) -> User:
    user = AsyncMock(spec=User)
    user.id = uid
    user.trips_folder = AsyncMock()
    return user


# ProcessingSession


class TestProcessingSession:
    @pytest.mark.anyio
    async def test_subscribe_gets_all_events(self) -> None:
        """Subscriber receives every event the processing run produces."""
        events = [
            TripStart(trip_index=0),
            PhaseUpdate(phase="elevations", done=1, total=5),
            PhaseUpdate(phase="weather", done=1, total=5),
        ]

        async def fake_processing(_user: User) -> AsyncIterator[ProcessingEvent]:
            for e in events:
                yield e

        with patch("app.logic.session.run_processing", fake_processing):
            session = ProcessingSession(_mock_user())
            result = await collect_async(session.subscribe())

        assert result == events
        assert session.is_done

    @pytest.mark.anyio
    async def test_replay_past_events_on_late_subscribe(self) -> None:
        """A subscriber that joins after processing completes gets all events."""
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

    @pytest.mark.anyio
    async def test_error_event_propagated(self) -> None:
        """Processing errors are yielded as ErrorData events."""

        async def fake_processing(_user: User) -> AsyncIterator[ProcessingEvent]:
            yield TripStart(trip_index=0)
            yield ErrorData()

        with patch("app.logic.session.run_processing", fake_processing):
            session = ProcessingSession(_mock_user())
            result = await collect_async(session.subscribe())

        assert len(result) == 2
        assert isinstance(result[1], ErrorData)


# process_stream (session management)


class TestProcessStream:
    @pytest.fixture(autouse=True)
    def _clean_sessions(self) -> Iterator[None]:
        _sessions.clear()
        yield
        _sessions.clear()

    @pytest.mark.anyio
    async def test_creates_new_session(self) -> None:
        """First call creates a new session and returns events."""
        events = [TripStart(trip_index=0)]

        async def fake_processing(_user: User) -> AsyncIterator[ProcessingEvent]:
            for e in events:
                yield e

        user = _mock_user(uid=42)
        with patch("app.logic.session.run_processing", fake_processing):
            result = await collect_async(process_stream(user))

        assert result == events

    @pytest.mark.anyio
    async def test_reconnect_to_running_session(self) -> None:
        """Second call while processing is running reconnects to same session."""
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

    @pytest.mark.anyio
    async def test_replays_completed_session(self) -> None:
        """After processing completes, a new call replays the same session."""
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

    @pytest.mark.anyio
    async def test_concurrent_same_user_shares_session(self) -> None:
        """Two concurrent calls for the same user share one session."""
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

    @pytest.mark.anyio
    async def test_session_kept_for_reconnection(self) -> None:
        """Completed sessions stay in _sessions for the TTL window."""

        async def fake_processing(_user: User) -> AsyncIterator[ProcessingEvent]:
            yield TripStart(trip_index=0)

        user = _mock_user(uid=3)
        with patch("app.logic.session.run_processing", fake_processing):
            await collect_async(process_stream(user))

        # Session stays alive for reconnection (evicted by call_later)
        assert user.id in _sessions
        assert _sessions[user.id].is_done

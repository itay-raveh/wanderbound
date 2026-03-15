"""Tests for the 'thumbs' phase in the processing pipeline."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest

from app.logic.processing import (
    PhaseUpdate,
    ProcessingEvent,
    ProcessingSession,
    TripStart,
)
from app.models.user import User
from tests.conftest import collect_async

# Helpers


def _mock_user(uid: int = 1) -> User:
    user = AsyncMock(spec=User)
    user.id = uid
    user.trips_folder = AsyncMock()
    return user


# Phase ordering


class TestThumbsPhaseInStream:
    @pytest.mark.anyio
    async def test_thumbs_phase_events_received(self) -> None:
        """Processing stream includes thumbs phase events."""
        events: list[ProcessingEvent] = [
            TripStart(trip_index=0),
            PhaseUpdate(phase="layouts", done=3, total=3),
            PhaseUpdate(phase="thumbs", done=0, total=5),
            PhaseUpdate(phase="thumbs", done=3, total=5),
            PhaseUpdate(phase="thumbs", done=5, total=5),
        ]

        async def fake_processing(_user: User) -> AsyncIterator[ProcessingEvent]:
            for e in events:
                yield e

        with patch("app.logic.processing._run_processing", fake_processing):
            session = ProcessingSession(_mock_user())
            result = await collect_async(session.subscribe())

        assert result == events

    @pytest.mark.anyio
    async def test_thumbs_after_frames(self) -> None:
        """Thumbs phase events come after frames phase in the stream."""
        events: list[ProcessingEvent] = [
            TripStart(trip_index=0),
            PhaseUpdate(phase="frames", done=0, total=2),
            PhaseUpdate(phase="frames", done=2, total=2),
            PhaseUpdate(phase="thumbs", done=0, total=4),
            PhaseUpdate(phase="thumbs", done=4, total=4),
        ]

        async def fake_processing(_user: User) -> AsyncIterator[ProcessingEvent]:
            for e in events:
                yield e

        with patch("app.logic.processing._run_processing", fake_processing):
            session = ProcessingSession(_mock_user())
            result = await collect_async(session.subscribe())

        thumbs_events = [
            e for e in result if isinstance(e, PhaseUpdate) and e.phase == "thumbs"
        ]
        frames_events = [
            e for e in result if isinstance(e, PhaseUpdate) and e.phase == "frames"
        ]

        assert len(thumbs_events) == 2
        assert len(frames_events) == 2

        # Thumbs events should appear after all frames events in the list
        last_frames_idx = max(result.index(e) for e in frames_events)
        first_thumbs_idx = min(result.index(e) for e in thumbs_events)
        assert first_thumbs_idx > last_frames_idx

    @pytest.mark.anyio
    async def test_thumbs_progress_increments(self) -> None:
        """Thumbs phase done counter increments from 0 to total."""
        events: list[ProcessingEvent] = [
            TripStart(trip_index=0),
            PhaseUpdate(phase="thumbs", done=0, total=3),
            PhaseUpdate(phase="thumbs", done=1, total=3),
            PhaseUpdate(phase="thumbs", done=2, total=3),
            PhaseUpdate(phase="thumbs", done=3, total=3),
        ]

        async def fake_processing(_user: User) -> AsyncIterator[ProcessingEvent]:
            for e in events:
                yield e

        with patch("app.logic.processing._run_processing", fake_processing):
            session = ProcessingSession(_mock_user())
            result = await collect_async(session.subscribe())

        thumbs = [
            e for e in result if isinstance(e, PhaseUpdate) and e.phase == "thumbs"
        ]
        assert thumbs[0].done == 0
        assert thumbs[-1].done == thumbs[-1].total == 3


class TestThumbsPhaseModel:
    def test_phase_update_accepts_thumbs(self) -> None:
        """PhaseUpdate can be constructed with phase='thumbs'."""
        update = PhaseUpdate(phase="thumbs", done=5, total=10)
        assert update.phase == "thumbs"
        assert update.done == 5
        assert update.total == 10

    def test_phase_update_serialization(self) -> None:
        """PhaseUpdate with 'thumbs' serializes correctly."""
        update = PhaseUpdate(phase="thumbs", done=2, total=8)
        data = update.model_dump()
        assert data == {"type": "phase", "phase": "thumbs", "done": 2, "total": 8}

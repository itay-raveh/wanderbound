"""Processing session management — SSE delivery with reconnect/replay.

Wraps the processing pipeline with a background task that stores events.
Clients subscribe to a session and receive all past + future events,
enabling reconnection without restarting work.
"""

import asyncio
import logging
from collections.abc import AsyncIterator

from app.logic.processing import ProcessingEvent, run_processing
from app.models.user import User

logger = logging.getLogger(__name__)

_SESSION_TTL = 300  # seconds before a completed session is evicted


def _evict_session(uid: int, session: ProcessingSession) -> None:
    """Remove a completed session if it hasn't been replaced."""
    if _sessions.get(uid) is session:
        del _sessions[uid]


class ProcessingSession:
    """Runs processing in a background task; clients subscribe to events."""

    def __init__(self, user: User) -> None:
        self._events: list[ProcessingEvent] = []
        self._done = False
        self._notify = asyncio.Event()
        self._uid = user.id
        self._task = asyncio.create_task(self._run(user))

    async def _run(self, user: User) -> None:
        try:
            async for event in run_processing(user):
                self._events.append(event)
                self._notify.set()
        finally:
            self._done = True
            self._notify.set()
            # Schedule cleanup so abandoned sessions don't leak memory.
            # Delay gives reconnecting clients time to attach.
            asyncio.get_running_loop().call_later(
                _SESSION_TTL,
                _evict_session,
                self._uid,
                self,
            )

    @property
    def is_done(self) -> bool:
        return self._done

    async def subscribe(self) -> AsyncIterator[ProcessingEvent]:
        """Yield all events (past and future) until processing completes."""
        idx = 0
        while True:
            while idx < len(self._events):
                yield self._events[idx]
                idx += 1
            if self._done:
                break
            self._notify.clear()
            # Re-check after clear to avoid race with producer
            if idx < len(self._events) or self._done:
                continue
            await self._notify.wait()


_sessions: dict[int, ProcessingSession] = {}


async def process_stream(user: User) -> AsyncIterator[ProcessingEvent]:
    """Start or reconnect to a user's processing session."""
    session = _sessions.get(user.id)

    if session is not None:
        logger.info(
            "User %d reconnecting to %s processing session",
            user.id,
            "completed" if session.is_done else "active",
        )
        async for event in session.subscribe():
            yield event
        return

    session = ProcessingSession(user)
    _sessions[user.id] = session

    async for event in session.subscribe():
        yield event

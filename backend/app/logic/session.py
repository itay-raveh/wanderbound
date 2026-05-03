"""Processing session management - SSE delivery with reconnect/replay.

Wraps the processing pipeline with a background task that stores events.
Clients subscribe to a session and receive all past + future events,
enabling reconnection without restarting work.
"""

import asyncio
from collections.abc import AsyncIterator

import structlog

from app.core.http_clients import HttpClients
from app.logic.segment_routes import schedule_album_route_enrichment
from app.logic.trip_pipeline import run_processing
from app.logic.trip_processing import ErrorData, ProcessingEvent
from app.models.user import User

logger = structlog.get_logger(__name__)

_SESSION_TTL = 300  # seconds before a completed session is evicted


class ProcessingSession:
    """Runs processing in a background task; clients subscribe to events."""

    def __init__(self, http: HttpClients, user: User) -> None:
        self._events: list[ProcessingEvent] = []
        self._done = False
        self._notify = asyncio.Event()
        self._uid = user.id
        self._task = asyncio.create_task(self._run(http, user))

    async def _run(self, http: HttpClients, user: User) -> None:
        saw_error = False
        try:
            async for event in run_processing(http, user):
                if isinstance(event, ErrorData):
                    saw_error = True
                self._events.append(event)
                self._notify.set()
            if not saw_error:
                for aid in user.album_ids:
                    schedule_album_route_enrichment(http, self._uid, aid)
        except Exception:
            logger.exception("processing.task_crashed", user_id=self._uid)
            # Surface the crash to subscribers; without this the stream ends
            # silently and the UI can't distinguish success from failure.
            self._events.append(ErrorData())
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

    @property
    def had_error(self) -> bool:
        return any(isinstance(e, ErrorData) for e in self._events)

    def cancel(self) -> None:
        self._task.cancel()

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


def _evict_session(uid: int, session: ProcessingSession) -> None:
    """Remove a completed session if it hasn't been replaced."""
    if _sessions.get(uid) is session:
        del _sessions[uid]


def cancel_all_sessions() -> None:
    """Cancel and remove all active processing sessions."""
    for uid in list(_sessions):
        cancel_session(uid)


def cancel_session(uid: int) -> None:
    """Cancel and remove any active processing session for a user."""
    session = _sessions.pop(uid, None)
    if session is not None and not session.is_done:
        session.cancel()
        logger.info("processing.session_cancelled", user_id=uid)


async def process_stream(
    http: HttpClients, user: User
) -> AsyncIterator[ProcessingEvent]:
    """Start or reconnect to a user's processing session.

    A finished session that ended in error is replaced with a fresh run so the
    user can retry without re-uploading. A finished session that succeeded is
    replayed so a browser refresh still works.
    """
    session = _sessions.get(user.id)

    if session is not None and not (session.is_done and session.had_error):
        if not session.is_done:
            logger.info("processing.session_reconnected", user_id=user.id)
        async for event in session.subscribe():
            yield event
        return

    if session is not None:
        logger.info("processing.session_retried", user_id=user.id)

    session = ProcessingSession(http, user)
    _sessions[user.id] = session

    async for event in session.subscribe():
        yield event

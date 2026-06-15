"""Processing session management - SSE delivery with reconnect/replay.

Wraps the processing pipeline with a background task that stores events.
Clients subscribe to a session and receive all past + future events,
enabling reconnection without restarting work.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import structlog
from sqlmodel import col, select

from app.core.http_clients import HttpClients
from app.logic.processing_operations import (
    append_processing_event,
    complete_processing_operation,
    create_processing_operation,
    latest_processing_operation,
    mark_processing_operation_running,
    read_processing_events,
)
from app.logic.segment_routes import schedule_album_route_enrichment
from app.logic.trip_pipeline import run_processing
from app.logic.trip_processing import ErrorData, ProcessingEvent
from app.logic.workflows.processing import start_processing_workflow
from app.models.processing import ProcessingOperation
from app.models.user import User

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.get_logger(__name__)

_SESSION_TTL = 300  # seconds before a completed session is evicted
_DB_POLL_INTERVAL = 0.05


class ProcessingSession:
    """Runs processing in a background task; clients subscribe to events."""

    def __init__(
        self,
        http: HttpClients,
        user: User,
        *,
        db_session: AsyncSession | None = None,
        operation: ProcessingOperation | None = None,
    ) -> None:
        self._events: list[ProcessingEvent] = []
        self._done = False
        self._notify = asyncio.Event()
        self._uid = user.id
        self._db_session = db_session
        self._operation = operation
        self._task = asyncio.create_task(self._run(http, user))

    async def _run(self, http: HttpClients, user: User) -> None:
        saw_error = False
        try:
            if self._db_session is not None and self._operation is not None:
                await mark_processing_operation_running(
                    self._db_session, self._operation
                )
                await self._db_session.commit()
            async for event in run_processing(http, user):
                if isinstance(event, ErrorData):
                    saw_error = True
                await self._record_event(event)
            if not saw_error:
                for aid in user.album_ids:
                    schedule_album_route_enrichment(http, self._uid, aid)
        except Exception:
            logger.exception("processing.task_crashed", user_id=self._uid)
            saw_error = True
            await self._record_event(ErrorData())
        finally:
            if self._db_session is not None and self._operation is not None:
                await complete_processing_operation(
                    self._db_session,
                    self._operation,
                    status="failed" if saw_error else "succeeded",
                )
                await self._db_session.commit()
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

    async def _record_event(self, event: ProcessingEvent) -> None:
        if self._db_session is not None and self._operation is not None:
            await append_processing_event(self._db_session, self._operation, event)
            await self._db_session.commit()
        self._events.append(event)
        self._notify.set()

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
    http: HttpClients, user: User, db_session: AsyncSession | None = None
) -> AsyncIterator[ProcessingEvent]:
    """Start or reconnect to a user's processing session.

    A finished session that ended in error is replaced with a fresh run so the
    user can retry without re-uploading. A finished session that succeeded is
    replayed so a browser refresh still works.
    """
    if db_session is not None:
        async for event in _persisted_process_stream(http, user, db_session):
            yield event
        return

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


async def _persisted_process_stream(
    http: HttpClients, user: User, db_session: AsyncSession
) -> AsyncIterator[ProcessingEvent]:
    operation = await _operation_for_process_request(db_session, user)
    await db_session.commit()

    if operation.status == "succeeded":
        for event in await read_processing_events(db_session, operation.operation_id):
            yield event
        return

    session = _sessions.get(user.id)
    if session is not None and not (session.is_done and session.had_error):
        async for event in session.subscribe():
            yield event
        return

    if operation.status != "running":
        start_processing_workflow(operation, user)

    async for event in _poll_persisted_operation(db_session, operation.operation_id):
        yield event


async def _operation_for_process_request(
    db_session: AsyncSession, user: User
) -> ProcessingOperation:
    await lock_user_for_processing_request(db_session, uid=user.id)
    latest = await latest_processing_operation(db_session, uid=user.id)
    if latest is None:
        return await create_processing_operation(
            db_session, uid=user.id, upload_generation=1
        )
    if latest.status in {"queued", "running", "succeeded"}:
        return latest
    return await create_processing_operation(
        db_session, uid=user.id, upload_generation=latest.upload_generation + 1
    )


async def lock_user_for_processing_request(
    db_session: AsyncSession, *, uid: int
) -> None:
    await db_session.exec(select(User).where(col(User.id) == uid).with_for_update())


async def _poll_persisted_operation(
    db_session: AsyncSession, operation_id: str
) -> AsyncIterator[ProcessingEvent]:
    after_seq = -1
    while True:
        events = await read_processing_events(
            db_session, operation_id, after_seq=after_seq
        )
        for event in events:
            after_seq += 1
            yield event

        status = await db_session.scalar(
            select(ProcessingOperation.status).where(
                col(ProcessingOperation.operation_id) == operation_id
            )
        )
        if status not in {"queued", "running"}:
            events = await read_processing_events(
                db_session, operation_id, after_seq=after_seq
            )
            for event in events:
                after_seq += 1
                yield event
            return

        await asyncio.sleep(_DB_POLL_INTERVAL)

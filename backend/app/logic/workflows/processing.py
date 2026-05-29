from typing import Any

import structlog
from dbos import DBOS, SetWorkflowID
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.core.http_clients import HttpClients
from app.logic.processing_operations import (
    append_processing_event,
    complete_processing_operation,
    mark_processing_operation_running,
    processing_operation_is_active,
    processing_operation_is_active_for_update,
)
from app.logic.segment_routes import schedule_album_route_enrichment
from app.logic.trip_pipeline import run_processing
from app.logic.trip_processing import ErrorData
from app.models.processing import ProcessingOperation
from app.models.user import User

logger = structlog.get_logger(__name__)


class ProcessingWorkflowPayload(BaseModel):
    operation_id: str
    uid: int
    upload_generation: int
    trips_folder: str
    album_ids: tuple[str, ...] = Field(default_factory=tuple)


def processing_workflow_payload(
    operation: ProcessingOperation, user: User
) -> dict[str, Any]:
    payload = ProcessingWorkflowPayload(
        operation_id=operation.operation_id,
        uid=operation.uid,
        upload_generation=operation.upload_generation,
        trips_folder=str(user.trips_folder),
        album_ids=tuple(user.album_ids),
    )
    return payload.model_dump(mode="json")


_workflow_http_clients: list[HttpClients] = []


def set_processing_workflow_http_clients(http: HttpClients | None) -> None:
    _workflow_http_clients.clear()
    if http is not None:
        _workflow_http_clients.append(http)


def get_processing_workflow_http_clients() -> HttpClients:
    if not _workflow_http_clients:
        msg = "processing workflow HTTP clients have not been initialized"
        raise RuntimeError(msg)
    return _workflow_http_clients[0]


async def run_processing_workflow_payload(
    payload: dict[str, Any], http: HttpClients, session: AsyncSession
) -> dict[str, str]:
    params = ProcessingWorkflowPayload.model_validate(payload)
    user = await session.get(User, params.uid)
    operation = await session.get(ProcessingOperation, params.operation_id)
    if user is None or operation is None:
        logger.info(
            "processing_workflow.cancelled_missing_rows",
            operation_id=params.operation_id,
            user_id=params.uid,
            missing_user=user is None,
            missing_operation=operation is None,
        )
        return {"operation_id": params.operation_id, "status": "cancelled"}

    if not await mark_processing_operation_running(session, operation):
        return {"operation_id": operation.operation_id, "status": operation.status}
    await session.commit()

    try:
        saw_error = await run_and_persist_processing_events(
            http, user, operation, session
        )
    except Exception as exc:
        await session.rollback()
        logger.exception(
            "processing_workflow.failed",
            operation_id=operation.operation_id,
            user_id=user.id,
            error_type=type(exc).__name__,
        )
        return await fail_active_processing_operation(session, operation, exc)

    status = "failed" if saw_error else "succeeded"
    if not await complete_processing_operation(session, operation, status=status):
        return {"operation_id": operation.operation_id, "status": operation.status}
    await session.commit()

    if not saw_error:
        for aid in user.album_ids:
            schedule_album_route_enrichment(http, user.id, aid)

    return {"operation_id": operation.operation_id, "status": status}


async def fail_active_processing_operation(
    session: AsyncSession,
    operation: ProcessingOperation,
    exc: Exception,
) -> dict[str, str]:
    current = await session.get(ProcessingOperation, operation.operation_id)
    if current is None:
        raise exc
    if not await processing_operation_is_active(session, current.operation_id):
        return {"operation_id": current.operation_id, "status": current.status}

    await append_processing_event(session, current, ErrorData())
    if not await complete_processing_operation(
        session,
        current,
        status="failed",
        error_code=type(exc).__name__,
    ):
        return {"operation_id": current.operation_id, "status": current.status}
    await session.commit()
    return {"operation_id": current.operation_id, "status": "failed"}


async def run_and_persist_processing_events(
    http: HttpClients,
    user: User,
    operation: ProcessingOperation,
    session: AsyncSession,
) -> bool:
    async def should_continue() -> bool:
        return await processing_operation_is_active(session, operation.operation_id)

    async def save_guard(save_session: AsyncSession) -> bool:
        return await processing_operation_is_active_for_update(
            save_session, operation.operation_id
        )

    saw_error = False
    async for event in run_processing(
        http, user, should_continue=should_continue, save_guard=save_guard
    ):
        if isinstance(event, ErrorData):
            saw_error = True
        await append_processing_event(session, operation, event)
        await session.commit()
    return saw_error


@DBOS.workflow(name="processing.upload")
async def processing_upload_workflow(payload: dict[str, Any]) -> dict[str, str]:
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        return await run_processing_workflow_payload(
            payload, get_processing_workflow_http_clients(), session
        )


def start_processing_workflow(operation: ProcessingOperation, user: User) -> object:
    with SetWorkflowID(operation.workflow_id):
        return DBOS.start_workflow(
            processing_upload_workflow,
            processing_workflow_payload(operation, user),
        )

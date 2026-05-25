from typing import Any

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
)
from app.logic.segment_routes import schedule_album_route_enrichment
from app.logic.trip_pipeline import run_processing
from app.logic.trip_processing import ErrorData
from app.models.processing import ProcessingOperation
from app.models.user import User


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
        msg = "processing workflow references missing user or operation"
        raise RuntimeError(msg)

    if not await processing_operation_is_active(session, operation.operation_id):
        return {"operation_id": operation.operation_id, "status": operation.status}

    await mark_processing_operation_running(session, operation)
    await session.commit()

    saw_error = await run_and_persist_processing_events(http, user, operation, session)

    await session.refresh(operation)
    if operation.status == "stale":
        return {"operation_id": operation.operation_id, "status": "stale"}

    status = "failed" if saw_error else "succeeded"
    await complete_processing_operation(session, operation, status=status)
    await session.commit()

    if not saw_error:
        for aid in user.album_ids:
            schedule_album_route_enrichment(http, user.id, aid)

    return {"operation_id": operation.operation_id, "status": status}


async def run_and_persist_processing_events(
    http: HttpClients,
    user: User,
    operation: ProcessingOperation,
    session: AsyncSession,
) -> bool:
    async def should_continue() -> bool:
        return await processing_operation_is_active(session, operation.operation_id)

    saw_error = False
    async for event in run_processing(http, user, should_continue=should_continue):
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

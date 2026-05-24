from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, SQLModel

from app.core.db import PydanticJSON

ProcessingOperationStatus = Literal[
    "queued", "running", "succeeded", "failed", "cancelled", "stale"
]
WorkflowExecutorStatus = Literal["active", "draining", "dead"]


def _now() -> datetime:
    return datetime.now(UTC)


def new_operation_id() -> str:
    return uuid4().hex


class ProcessingOperation(SQLModel, table=True):
    __tablename__ = "processing_operation"
    __table_args__ = (
        sa.Index(
            "ix_processing_operation_uid_generation_created",
            "uid",
            "upload_generation",
            "created_at",
        ),
    )

    operation_id: str = Field(default_factory=new_operation_id, primary_key=True)
    uid: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    upload_generation: int = Field(index=True)
    workflow_id: str = Field(unique=True, index=True, max_length=255)
    status: ProcessingOperationStatus = Field(
        default="queued",
        sa_column=Column(String(20), nullable=False, index=True),
    )
    started_by_executor_id: str | None = Field(default=None, max_length=255)
    error_code: str | None = Field(default=None, max_length=100)
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ProcessingEventRow(SQLModel, table=True):
    __tablename__ = "processing_event"

    operation_id: str = Field(
        foreign_key="processing_operation.operation_id",
        primary_key=True,
        ondelete="CASCADE",
    )
    seq: int = Field(primary_key=True)
    event_type: str = Field(max_length=50, index=True)
    payload: dict[str, object] = Field(
        sa_column=Column(PydanticJSON(dict), nullable=False)
    )
    created_at: datetime = Field(
        default_factory=_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class WorkflowExecutorHeartbeat(SQLModel, table=True):
    __tablename__ = "workflow_executor_heartbeat"

    executor_id: str = Field(primary_key=True, max_length=255)
    admin_base_url: str = Field(max_length=500)
    status: WorkflowExecutorStatus = Field(
        default="active",
        sa_column=Column(String(20), nullable=False, index=True),
    )
    last_seen_at: datetime = Field(
        default_factory=_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )

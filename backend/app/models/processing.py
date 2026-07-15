from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Literal, Self
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import BigInteger, Column, DateTime, String, Text
from sqlmodel import Field, SQLModel

from app.core.db import PydanticJSON
from app.models.upload import UploadResult

ProcessingOperationStatus = Literal[
    "queued", "running", "succeeded", "failed", "cancelled", "stale"
]
WorkflowExecutorStatus = Literal["active", "draining", "dead"]
UploadStatus = Literal[
    "uploading",
    "processing",
    "succeeded",
    "failed",
    "aborted",
]
UPLOAD_PART_SIZE_BYTES = 67_108_864


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


class UploadSession(SQLModel, table=True):
    __tablename__ = "upload_session"
    __table_args__ = (
        sa.Index("ix_upload_session_owner_status", "owner", "status"),
        sa.Index("ix_upload_session_expires_at", "expires_at"),
        sa.Index("uq_upload_session_object_key", "object_key", unique=True),
    )

    upload_id: str = Field(primary_key=True, max_length=255)
    owner: str = Field(max_length=255)
    object_key: str = Field(max_length=500)
    provider_upload_id: str = Field(sa_column=Column(Text, nullable=False))
    filename: str = Field(sa_column=Column(Text, nullable=False))
    content_type: str = Field(max_length=255)
    size_bytes: int = Field(sa_column=Column(BigInteger, nullable=False))
    status: UploadStatus = Field(
        default="uploading",
        sa_column=Column(String(20), nullable=False),
    )
    error_code: str | None = Field(default=None, max_length=100)
    result: UploadResult | None = Field(
        default=None, sa_column=Column(PydanticJSON(UploadResult), nullable=True)
    )
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    created_at: datetime = Field(
        default_factory=_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    completed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    @classmethod
    def new(  # noqa: PLR0913
        cls,
        *,
        owner: str,
        provider_upload_id: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        ttl_seconds: int = 86_400,
    ) -> Self:
        upload_id = token_urlsafe(24)
        return cls(
            upload_id=upload_id,
            owner=owner,
            object_key=f"uploads/{upload_id}.zip",
            provider_upload_id=provider_upload_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            expires_at=_now() + timedelta(seconds=ttl_seconds),
        )


class ArtifactToken(SQLModel, table=True):
    __tablename__ = "artifact_token"

    token: str = Field(primary_key=True, max_length=255)
    namespace: str = Field(max_length=100, index=True)
    path: str
    payload: dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(PydanticJSON(dict[str, str]), nullable=False),
    )
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
    created_at: datetime = Field(
        default_factory=_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

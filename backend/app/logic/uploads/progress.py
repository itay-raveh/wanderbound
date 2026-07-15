from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

UploadIngestionPhase = Literal["downloading", "validating", "importing"]


class UploadProgressUpdate(BaseModel):
    type: Literal["progress"] = "progress"
    phase: UploadIngestionPhase
    done: int
    total: int


class UploadCompleteEvent(BaseModel):
    type: Literal["complete"] = "complete"


class UploadErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    error_code: str


UploadWorkflowEvent = Annotated[
    UploadProgressUpdate | UploadCompleteEvent | UploadErrorEvent,
    Field(discriminator="type"),
]
UploadProgressEvent = UploadWorkflowEvent

UPLOAD_WORKFLOW_EVENT_ADAPTER = TypeAdapter(UploadWorkflowEvent)

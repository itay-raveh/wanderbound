from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

UploadIngestionPhase = Literal["downloading", "validating", "importing"]


class UploadPhaseEvent(BaseModel):
    type: Literal["phase"] = "phase"
    phase: UploadIngestionPhase


class UploadCompleteEvent(BaseModel):
    type: Literal["complete"] = "complete"


class UploadErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    error_code: str


UploadWorkflowEvent = Annotated[
    UploadPhaseEvent | UploadCompleteEvent | UploadErrorEvent,
    Field(discriminator="type"),
]
UploadProgressEvent = UploadWorkflowEvent

UPLOAD_WORKFLOW_EVENT_ADAPTER = TypeAdapter(UploadWorkflowEvent)

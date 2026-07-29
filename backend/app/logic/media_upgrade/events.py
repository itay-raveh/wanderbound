from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .phash_matching import MatchResult


class MatchInProgress(BaseModel):
    type: Literal["match_in_progress"] = "match_in_progress"
    phase: str
    done: int
    total: int


class DownloadInProgress(BaseModel):
    type: Literal["download_in_progress"] = "download_in_progress"
    done: int
    total: int


class MatchCompleted(BaseModel):
    type: Literal["match_completed"] = "match_completed"
    total_picked: int
    matched: int
    unmatched: int
    matches: list[MatchResult]


class UpgradeCompleted(BaseModel):
    type: Literal["upgrade_completed"] = "upgrade_completed"
    replaced: int
    skipped: int
    failed: int


class UpgradeFailed(BaseModel):
    type: Literal["upgrade_failed"] = "upgrade_failed"
    detail: str


UpgradeEvent = Annotated[
    MatchInProgress
    | DownloadInProgress
    | MatchCompleted
    | UpgradeCompleted
    | UpgradeFailed,
    Field(discriminator="type"),
]

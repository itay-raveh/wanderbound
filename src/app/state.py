from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from src.models.args import GeneratorArgs
    from src.models.context import TripTemplateCtx
    from src.models.trip import EnrichedStep, Location


class AppState:
    def __init__(self) -> None:
        self.args: GeneratorArgs | None = None
        self.trip_ctx: TripTemplateCtx | None = None
        self.steps: Sequence[EnrichedStep] = []
        self.home_location: tuple[Location, str] | None = None
        self.layout_file: Path | None = None

    def is_ready(self) -> bool:
        return self.layout_file is not None and self.layout_file.exists()


state = AppState()

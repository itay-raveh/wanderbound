from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Self

from anyio import Path
from nicegui import app
from nicegui.binding import bindable_dataclass  # pyright: ignore[reportUnusedImport]

from psagen.core.settings import settings

type TripName = str


@(dataclass if TYPE_CHECKING else bindable_dataclass)
class User:
    id: str
    trip_names: list[TripName]
    selected_trip: TripName

    @property
    def folder(self) -> Path:
        return Path(settings.users_dir) / self.id

    @property
    def trips_folder(self) -> Path:
        return self.folder / "trip"

    @classmethod
    def from_storage(cls) -> Self:
        return cls(**app.storage.user)  # pyright: ignore[reportUnknownArgumentType]

    def store(self) -> None:
        # noinspection PyTypeChecker,PyDataclass
        app.storage.user.update(asdict(self))

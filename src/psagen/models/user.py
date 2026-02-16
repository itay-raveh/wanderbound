from dataclasses import asdict
from pathlib import Path

from nicegui import app
from nicegui.binding import bindable_dataclass

from psagen.core.settings import settings

type TripName = str


@bindable_dataclass
class User:
    id: str
    trip_names: list[TripName]
    selected_trip: TripName | None = None

    @property
    def folder(self) -> Path:
        return settings.users_dir / self.id

    @property
    def trips_folder(self) -> Path:
        return self.folder / "trip"


def get_user() -> User:
    return User(**app.storage.user)


def set_user(user: User) -> None:
    app.storage.user.update(asdict(user))

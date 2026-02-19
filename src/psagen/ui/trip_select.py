from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import app, ui

if TYPE_CHECKING:
    from psagen.models.user import TripName, User


def trip_select_for(user: User) -> ui.select:
    return (
        ui.select(_trips_with_labels(user.trip_names), value=user.selected_trip)
        .classes("w-full text-xl font-medium")
        .props("outlined")
        .bind_value_to(user, "selected_trip")
        .bind_value_to(app.storage.user, "selected_trip")
    )


def _trips_with_labels(trip_names: list[TripName]) -> dict[TripName, str]:
    return {name: name[: name.find("_")].title() for name in trip_names}

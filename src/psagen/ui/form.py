from contextlib import suppress
from functools import partial
from typing import Self, cast, get_args

from geopy.adapters import AioHTTPAdapter
from geopy.geocoders.nominatim import Nominatim
from nicegui import ui
from nicegui.binding import BindableProperty
from nicegui.elements.mixins.validation_element import ValidationFunction
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic.fields import FieldInfo

from psagen.core.logger import get_logger
from psagen.models.trip import Location

logger = get_logger(__name__)

_JS_GET_USER_LOC_OR_ERR_MSG = """
return await new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
        resolve("Geolocation not supported");
    } else {
        navigator.geolocation.getCurrentPosition(
            (pos) => resolve({lat: pos.coords.latitude, lon: pos.coords.longitude}),
            (err) => resolve(err.message),
            {timeout: 10000}
        );
    }
});
"""


async def _try_get_user_location() -> Location | None:
    # NiceGUI won't let us run JS without a timeout,
    # so we just have this default error in case the user...
    # needs some time to think about it?
    res: dict[str, float] | str = "To use this feature, you must click 'Allow' in the popup"
    with suppress(TimeoutError):
        res = cast(
            "dict[str, float] | str",
            await ui.run_javascript(_JS_GET_USER_LOC_OR_ERR_MSG, timeout=30),
        )

    if isinstance(res, str):
        ui.notify(f"Failed: {res}", type="negative")
        return None

    async with Nominatim(user_agent="psagen", adapter_factory=AioHTTPAdapter) as geolocator:
        loc = await geolocator.reverse((res["lat"], res["lon"]), zoom=12, language="en")

    if loc is None:
        ui.notify("Failed: try again", type="negative")
        return None

    return Location(**loc.raw["address"], **res)  # pyright: ignore[reportArgumentType]


def _make_input_validation[T](field: FieldInfo) -> ValidationFunction:
    ta = TypeAdapter[T](field.annotation)

    def validation(value: T) -> str | None:
        if value is None or value == "":
            return "Required!" if field.is_required() else None

        try:
            ta.validate_python(value)
        except ValidationError as e:
            return "\n".join(err["msg"].removeprefix("Value error, ") for err in e.errors())

    return validation


class PydanticForm:
    instance = BindableProperty(on_change=lambda sender, _: cast("Self", sender)._render())  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType, reportAssignmentType]  # noqa: SLF001
    errors = BindableProperty()

    def __init__(self) -> None:
        self.instance: BaseModel | None = None
        self.column = ui.column()
        self.errors = set[str]()

    def _on_value_change(self, name: str, inp: ui.input) -> None:
        if inp.validate():
            setattr(self.instance, name, inp.value)  # pyright: ignore[reportAny]
            self.errors -= {name}
        else:
            self.errors.add(name)

    async def _on_location_refresh(self, name: str, inp: ui.input) -> None:
        if location := await _try_get_user_location():
            setattr(self.instance, name, location)
            inp.value = str(location)

    def _render_field(self, name: str, field: FieldInfo) -> None:
        if field.annotation is None:
            return

        inp = (
            ui.input(
                value=str(getattr(self.instance, name) or ""),
                label=name.replace("_", " ").title(),
            )
            .classes("w-full")
            .props("dense outlined rounded")
        )

        if field.description:
            inp.props(f'hint="{field.description}"')
        if field.examples:
            inp.props(f'placeholder="{field.examples[0]}"')

        if Location in get_args(field.annotation) or field.annotation is Location:
            inp.props("readonly")
            with inp:
                ui.button(
                    icon="refresh", on_click=partial(self._on_location_refresh, name, inp)
                ).props("flat dense")
        else:
            inp.validation = _make_input_validation(field)
            inp.on_value_change(partial(self._on_value_change, name, inp))

    def _render(self) -> None:
        self.column.clear()

        if self.instance is None:
            return

        with self.column:
            for name, field in self.instance.__class__.model_fields.items():
                self._render_field(name, field)

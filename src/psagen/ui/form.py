from functools import partial
from typing import Self, cast

from nicegui import ui
from nicegui.binding import BindableProperty
from nicegui.elements.mixins.validation_element import ValidationFunction
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic.fields import FieldInfo

from psagen.core.logger import get_logger

logger = get_logger(__name__)


def _make_input_validation[T](field: FieldInfo) -> ValidationFunction:
    ta = TypeAdapter[T](field.annotation)

    def validation(value: T) -> str | None:
        if value == "":
            return "Required!" if field.is_required() else None

        try:
            ta.validate_python(value)
        except ValidationError as e:
            return "\n".join(err["msg"].removeprefix("Value error, ") for err in e.errors())

    return validation


class PydanticForm:
    instance = BindableProperty(on_change=lambda sender, value: cast("Self", sender)._render(value))  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType]  # noqa: SLF001
    ready = BindableProperty()

    def __init__(self) -> None:
        self.instance = None
        self.ready = True

        self._elem = ui.element()
        self._errors = set[str]()

    def _on_value_change(self, name: str, inp: ui.input) -> None:
        if inp.validate():
            setattr(self.instance, name, inp.value)  # pyright: ignore[reportAny]
            self._errors -= {name}
        else:
            self._errors.add(name)

        self.ready = len(self._errors) == 0

    def _render(self, instance: BaseModel | None) -> None:
        self._elem.clear()

        if not instance:
            return

        with self._elem:
            for name, field in instance.__class__.model_fields.items():
                if field.annotation is None:
                    continue

                inp = ui.input(
                    value=str(getattr(instance, name)),  # pyright: ignore[reportAny]
                    label=name.replace("_", " ").title(),
                    validation=_make_input_validation(field),
                ).classes("w-full rounded-lg")

                inp.on_value_change(partial(self._on_value_change, name, inp))

                if field.description:
                    inp.props(f"hint='{field.description}")
                if field.examples:
                    inp.props(f"placeholder='{field.examples[0]}'")

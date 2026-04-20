import copy
from functools import cache
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import String, TypeDecorator
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import JSON, SQLModel

from app.core.config import get_settings
from app.core.encryption import encrypt_token, try_decrypt_token


class PydanticJSON(TypeDecorator[Any]):
    """JSON column that round-trips via Pydantic TypeAdapter."""

    impl = JSON
    cache_ok = True

    def __init__(self, tp: Any) -> None:
        super().__init__()
        self._adapter = TypeAdapter(tp)

    def process_bind_param(self, value: Any, dialect: Any) -> Any:  # noqa: ARG002
        if value is None:
            return None
        return self._adapter.dump_python(value, mode="json")

    def process_result_value(self, value: Any, dialect: Any) -> Any:  # noqa: ARG002
        if value is None:
            return None
        return self._adapter.validate_python(value)


class EncryptedString(TypeDecorator[str]):
    """Fernet-encrypted string column. Decrypt returns None after key rotation."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:  # noqa: ARG002
        return encrypt_token(value) if value is not None else None

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:  # noqa: ARG002
        return try_decrypt_token(value) if value is not None else None


def all_optional[T: SQLModel](cls: type[T]) -> type[T]:
    """Make all fields Optional with default None (for PATCH update models)."""
    for name in list(cls.model_fields):
        patched = copy.copy(cls.model_fields[name])
        if patched.is_required():
            patched.default = None
        patched.annotation = patched.annotation | None
        cls.model_fields[name] = patched
    cls.model_rebuild(force=True)
    return cls


@cache
def get_engine() -> AsyncEngine:
    return create_async_engine(
        str(get_settings().SQLALCHEMY_DATABASE_URI),
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
    )

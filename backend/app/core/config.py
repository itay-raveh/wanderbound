from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AnyUrl,
    BeforeValidator,
    Field,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.resources import detect_storage_bytes

# Reserve 10% of detected storage for DB WAL, logs, temp files, uploads
_STORAGE_HEADROOM = 0.9


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    if isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )

    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    VITE_FRONTEND_URL: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "production"] = "local"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    SENTRY_DSN: str | None = None
    SENTRY_RELEASE: str | None = None

    VITE_GOOGLE_CLIENT_ID: str = ""
    VITE_MICROSOFT_CLIENT_ID: str = ""
    GOOGLE_PHOTOS_CLIENT_SECRET: str = ""
    VITE_MAX_UPLOAD_GB: int = 4

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.VITE_FRONTEND_URL
        ]

    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    VITE_MAPBOX_TOKEN: str | None = None

    DATA_FOLDER: Path = Field(default=Path("./data").resolve())
    MAX_STORAGE_BYTES: int = 0

    @model_validator(mode="after")
    def _detect_storage_cap(self) -> Self:
        if not self.MAX_STORAGE_BYTES:
            self.MAX_STORAGE_BYTES = int(
                detect_storage_bytes(self.DATA_FOLDER) * _STORAGE_HEADROOM
            )
        return self

    @model_validator(mode="after")
    def _require_in_production(self) -> Self:
        if self.ENVIRONMENT != "production":
            return self
        missing: list[str] = []
        if not self.VITE_MAPBOX_TOKEN:
            missing.append("VITE_MAPBOX_TOKEN")
        if "localhost" in self.VITE_FRONTEND_URL:
            missing.append("VITE_FRONTEND_URL")
        if not self.VITE_GOOGLE_CLIENT_ID and not self.VITE_MICROSOFT_CLIENT_ID:
            missing.append("VITE_GOOGLE_CLIENT_ID or VITE_MICROSOFT_CLIENT_ID")
        if missing:
            raise ValueError(f"required in production: {', '.join(missing)}")
        return self

    @property
    def USERS_FOLDER(self) -> Path:
        return self.DATA_FOLDER / "users"

    DEMO_FIXTURES: Path = Field(
        default=Path(__file__).resolve().parents[3] / "fixtures" / "demo"
    )


@cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

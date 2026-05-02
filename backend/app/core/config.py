from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AnyHttpUrl,
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

_DOCKER_SECRETS_DIR = Path("/run/secrets")


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    if isinstance(v, list | str):
        return v
    raise ValueError(v)


def ensure_psycopg_scheme(v: Any) -> Any:
    # SQLAlchemy's +psycopg suffix selects psycopg3; CNPG/Heroku/Render emit
    # plain postgresql://, so rewrite at ingest rather than at each consumer.
    if isinstance(v, str) and v.startswith("postgresql://"):
        return "postgresql+psycopg://" + v.removeprefix("postgresql://")
    return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        secrets_dir=_DOCKER_SECRETS_DIR if _DOCKER_SECRETS_DIR.is_dir() else None,
        env_ignore_empty=True,
        extra="ignore",
    )

    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    SECRET_KEY_PREVIOUS: str | None = None
    VITE_FRONTEND_URL: AnyHttpUrl = AnyHttpUrl("http://localhost:5173")
    FRONTEND_URL: AnyHttpUrl | None = None
    ENVIRONMENT: Literal["local", "production"] = "local"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    APP_VERSION: str | None = None

    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default=0.1, ge=0, le=1)

    VITE_GOOGLE_CLIENT_ID: str = ""
    VITE_MICROSOFT_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    VITE_MAX_UPLOAD_GB: int = 4

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            str(self.VITE_FRONTEND_URL).rstrip("/")
        ]

    SQLALCHEMY_DATABASE_URI: Annotated[
        PostgresDsn, BeforeValidator(ensure_psycopg_scheme)
    ]

    VITE_MAPBOX_TOKEN: str | None = None

    DATA_FOLDER: Path = Field(default=Path("./data").resolve())
    MAX_STORAGE_BYTES: int = 0

    @model_validator(mode="after")
    def _default_frontend_url(self) -> Self:
        if self.FRONTEND_URL is None:
            self.FRONTEND_URL = self.VITE_FRONTEND_URL
        return self

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
        if "localhost" in str(self.VITE_FRONTEND_URL):
            missing.append("VITE_FRONTEND_URL")
        if not self.VITE_GOOGLE_CLIENT_ID and not self.VITE_MICROSOFT_CLIENT_ID:
            missing.append("VITE_GOOGLE_CLIENT_ID or VITE_MICROSOFT_CLIENT_ID")
        if self.VITE_GOOGLE_CLIENT_ID and not self.GOOGLE_CLIENT_SECRET:
            missing.append("GOOGLE_CLIENT_SECRET")
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
    return Settings()  # type: ignore[call-arg]  # ty: ignore[missing-argument]

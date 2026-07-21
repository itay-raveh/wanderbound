from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AnyHttpUrl,
    AnyUrl,
    BaseModel,
    BeforeValidator,
    Field,
    PostgresDsn,
    SecretStr,
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


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        secrets_dir=_DOCKER_SECRETS_DIR if _DOCKER_SECRETS_DIR.is_dir() else None,
        env_ignore_empty=True,
        extra="ignore",
    )

    SQLALCHEMY_DATABASE_URI: Annotated[
        PostgresDsn, BeforeValidator(ensure_psycopg_scheme)
    ]


class PublicSettings(BaseModel):
    ENVIRONMENT: Literal["local", "production"] = "local"
    APP_VERSION: str | None = None
    PUBLIC_URL: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    GOOGLE_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_ID: str = ""
    MAX_UPLOAD_SIZE_BYTES: int = Field(default=4 * 1024**3, ge=1, le=4 * 1024**3)
    MAPBOX_TOKEN: str | None = None
    CONTACT_EMAIL: str | None = None
    GITHUB_URL: AnyHttpUrl | None = None
    AUTHOR_NAME: str | None = None
    AUTHOR_URL: AnyHttpUrl | None = None
    PUBLIC_SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default=0.1, ge=0, le=1)


class Settings(PublicSettings, DatabaseSettings):
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    SECRET_KEY_PREVIOUS: str | None = None
    INTERNAL_URL: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8000")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    DBOS_APP_NAME: str = "wanderbound"
    DBOS_SYSTEM_DATABASE_URI: SecretStr | None = None
    DBOS_EXECUTOR_ID: str | None = None
    DBOS_ADMIN_PORT: int = 3001
    DBOS_RUN_ADMIN_SERVER: bool = True
    DBOS_HEARTBEAT_TTL_SECONDS: float = 60.0
    DBOS_RECOVERY_INTERVAL_SECONDS: float = 10.0

    SENTRY_DSN: str | None = None

    GOOGLE_CLIENT_SECRET: str = ""

    UPLOAD_S3_BUCKET: str = "wanderbound-uploads"
    UPLOAD_S3_REGION: str = "garage"
    UPLOAD_S3_INTERNAL_ENDPOINT_URL: AnyHttpUrl = AnyHttpUrl("http://localhost:3900")
    UPLOAD_S3_PUBLIC_ENDPOINT_URL: AnyHttpUrl = AnyHttpUrl("http://localhost:3900")
    UPLOAD_S3_ADDRESSING_STYLE: Literal["path", "virtual"] = "path"
    UPLOAD_S3_ACCESS_KEY_ID: str
    UPLOAD_S3_SECRET_ACCESS_KEY: SecretStr
    UPLOAD_S3_PRESIGN_TTL_SECONDS: int = Field(default=900, ge=1, le=900)
    UPLOAD_SESSION_TTL_SECONDS: int = 86_400

    CORS_ORIGINS: Annotated[list[AnyUrl] | str, BeforeValidator(parse_cors)] = []

    @computed_field
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.CORS_ORIGINS] + [
            str(self.PUBLIC_URL).rstrip("/")
        ]

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
        if not self.MAPBOX_TOKEN:
            missing.append("MAPBOX_TOKEN")
        if "localhost" in str(self.PUBLIC_URL):
            missing.append("PUBLIC_URL")
        if not self.GOOGLE_CLIENT_ID and not self.MICROSOFT_CLIENT_ID:
            missing.append("GOOGLE_CLIENT_ID or MICROSOFT_CLIENT_ID")
        if self.GOOGLE_CLIENT_ID and not self.GOOGLE_CLIENT_SECRET:
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

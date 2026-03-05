from pathlib import Path

from pydantic import AnyUrl, Field, PostgresDsn, UrlConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict


class SqliteDsn(AnyUrl):
    _constraints = UrlConstraints(
        allowed_schemes=["sqlite", "sqlite+aiosqlite"],
    )


class Settings(BaseSettings):
    db_conn_uri: PostgresDsn | SqliteDsn

    data_dir: Path = Field(default=Path("./data").resolve())

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def users_dir(self) -> Path:
        return self.data_dir / "users"

    visual_crossing_api_key: str | None = None

    # Display settings
    long_description_threshold: int = Field(default=1000, gt=0)
    extra_long_description_threshold: int = Field(default=4350, gt=0)
    feels_like_display_threshold: float = Field(default=3.0, ge=0.0)

    model_config = SettingsConfigDict(
        env_prefix="PSAGEN_",
        env_file=".env",
        env_file_encoding="utf-8",
    )


# noinspection PyArgumentList
settings = Settings()  # pyright: ignore[reportCallIssue]

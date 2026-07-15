import subprocess
import sys
from pathlib import Path


def test_migrations_require_only_database_configuration(tmp_path: Path) -> None:
    backend = Path(__file__).resolve().parents[1]
    alembic_config = tmp_path / "alembic.ini"
    alembic_config.write_text(
        (backend / "alembic.ini")
        .read_text()
        .replace(
            "script_location = app/alembic",
            f"script_location = {backend}/app/alembic",
        )
    )

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(alembic_config),
            "upgrade",
            "f097a964b67c",
            "--sql",
        ],
        cwd=tmp_path,
        env={
            "PYTHONPATH": str(backend),
            "SQLALCHEMY_DATABASE_URI": (
                "postgresql://wanderbound:secret@database/wanderbound"
            ),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr

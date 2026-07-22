import os
import subprocess
from pathlib import Path


def test_start_script_migrates_then_executes_uvicorn(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    trace = tmp_path / "trace"

    (bin_dir / "alembic").write_text(
        '#!/bin/sh\nprintf "alembic %s\\n" "$*" >> "$TRACE"\n'
    )
    (bin_dir / "uvicorn").write_text(
        '#!/bin/sh\nprintf "uvicorn %s\\n" "$*" >> "$TRACE"\n'
    )
    (bin_dir / "alembic").chmod(0o755)
    (bin_dir / "uvicorn").chmod(0o755)

    repository = Path(__file__).resolve().parents[2]
    result = subprocess.run(  # noqa: S603
        [repository / "scripts" / "start.sh", "--reload"],
        check=False,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TRACE": str(trace),
        },
        text=True,
    )

    assert result.returncode == 0
    assert trace.read_text().splitlines() == [
        "alembic upgrade head",
        "uvicorn app.main:app --host 0.0.0.0 --port 8000 "
        "--log-config app/core/uvicorn_logging.json --reload",
    ]


def test_sourcemap_upload_validates_and_waits_for_processing(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    trace = tmp_path / "trace"

    (bin_dir / "sentry-cli").write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TRACE"\n')
    (bin_dir / "sentry-cli").chmod(0o755)

    repository = Path(__file__).resolve().parents[2]
    result = subprocess.run(  # noqa: S603
        ["/bin/sh", repository / "scripts" / "upload_sourcemaps.sh"],
        check=False,
        capture_output=True,
        env={
            **os.environ,
            "APP_VERSION": "v1.8.0",
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TRACE": str(trace),
        },
        text=True,
    )

    assert result.returncode == 0
    assert trace.read_text().splitlines() == [
        "releases new wanderbound@1.8.0",
        "sourcemaps upload --release wanderbound@1.8.0 --validate --wait "
        "/app/sourcemaps",
        "releases finalize wanderbound@1.8.0",
    ]

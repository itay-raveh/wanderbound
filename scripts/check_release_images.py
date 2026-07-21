#!/usr/bin/env python3

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_IMAGE = os.environ.get("APP_IMAGE", "wanderbound:dev")
SOURCEMAPS_IMAGE = os.environ.get("SOURCEMAPS_IMAGE", "wanderbound-sourcemaps:dev")


def run(*args: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def copy_from_image(image: str, source: str, destination: Path) -> None:
    container = run("docker", "create", image, capture_output=True).stdout.strip()
    try:
        run("docker", "cp", f"{container}:{source}", str(destination))
    finally:
        run("docker", "rm", container, capture_output=True)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_setting_names() -> set[str]:
    document = json.loads((ROOT / "backend/openapi.json").read_text())
    return set(document["components"]["schemas"]["PublicSettings"]["properties"])


def assert_image_environment_is_neutral(image: str) -> None:
    result = run(
        "docker",
        "image",
        "inspect",
        image,
        "--format",
        "{{json .Config.Env}}",
        capture_output=True,
    )
    names = {entry.partition("=")[0] for entry in json.loads(result.stdout)}
    forbidden = (public_setting_names() - {"APP_VERSION"}) | {
        name for name in names if name.startswith("VITE_")
    }
    leaked = sorted(names & forbidden)
    if leaked:
        raise AssertionError(f"{image} embeds installation settings: {leaked}")


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        app = directory / "app"
        sourcemaps = directory / "sourcemaps"
        copy_from_image(APP_IMAGE, "/app/frontend/dist", app)
        copy_from_image(SOURCEMAPS_IMAGE, "/sourcemaps", sourcemaps)

        app_javascript = {
            path.relative_to(app): digest(path) for path in app.rglob("*.js")
        }
        sourcemap_javascript = {
            path.relative_to(sourcemaps): digest(path)
            for path in sourcemaps.rglob("*.js")
        }

        if not (app / "index.html").is_file():
            raise AssertionError("application image has no frontend index.html")
        if list(app.rglob("*.map")):
            raise AssertionError("application image contains source maps")
        if not app_javascript:
            raise AssertionError("application image contains no JavaScript")
        if app_javascript != sourcemap_javascript:
            raise AssertionError("application and source-map JavaScript differ")
        if not list(sourcemaps.rglob("*.map")):
            raise AssertionError("source-map image contains no source maps")

        assert_image_environment_is_neutral(APP_IMAGE)
        assert_image_environment_is_neutral(SOURCEMAPS_IMAGE)

    print(f"Verified {APP_IMAGE} and {SOURCEMAPS_IMAGE}")


if __name__ == "__main__":
    main()

import argparse
import json
import re
import subprocess
import sys


DEBUG_ID = re.compile(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def run(*command: str) -> bytes:
    return subprocess.run(command, check=True, capture_output=True).stdout


def shell(image: str, command: str) -> bytes:
    return run("docker", "run", "--rm", "--entrypoint", "sh", image, "-c", command)


def inspect(image: str) -> dict[str, object]:
    return json.loads(run("docker", "image", "inspect", image))[0]


def environment(image_data: dict[str, object]) -> dict[str, str]:
    config = image_data["Config"]
    assert isinstance(config, dict)
    values = config.get("Env") or []
    assert isinstance(values, list)
    return dict(value.split("=", 1) for value in values)


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def debug_ids(image: str, root: str) -> set[bytes]:
    javascript = shell(image, f"find {root} -type f -name '*.js' -exec cat {{}} +")
    return set(DEBUG_ID.findall(javascript))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("frontend")
    parser.add_argument("sourcemaps")
    args = parser.parse_args()

    frontend = inspect(args.frontend)
    sourcemaps = inspect(args.sourcemaps)
    frontend_env = environment(frontend)
    sourcemaps_env = environment(sourcemaps)

    maps = shell(
        args.frontend,
        "find /usr/share/nginx/html -type f -name '*.map' -print",
    )
    if maps:
        fail("frontend image contains source maps")

    artifact_files = (
        shell(args.sourcemaps, "find /artifacts -type f -print | sort")
        .decode()
        .splitlines()
    )
    if not any(path.endswith(".js") for path in artifact_files):
        fail("source-map image contains no JavaScript")
    if not any(path.endswith(".map") for path in artifact_files):
        fail("source-map image contains no source maps")

    frontend_ids = debug_ids(args.frontend, "/usr/share/nginx/html/assets")
    sourcemap_ids = debug_ids(args.sourcemaps, "/artifacts/assets")
    if not frontend_ids:
        fail("frontend JavaScript contains no debug IDs")
    if frontend_ids != sourcemap_ids:
        fail("frontend and source-map debug IDs differ")

    if frontend_env.get("APP_VERSION") != sourcemaps_env.get("APP_VERSION"):
        fail("frontend and source-map APP_VERSION values differ")
    if not frontend_env.get("APP_VERSION"):
        fail("paired images have no APP_VERSION")

    for image, values in (
        (args.frontend, frontend_env),
        (args.sourcemaps, sourcemaps_env),
    ):
        installation_names = [
            name for name in values if name.startswith(("VITE_", "SENTRY_"))
        ]
        if installation_names:
            fail(f"{image} contains installation environment values")

    print(
        f"validated {len(frontend_ids)} debug IDs across "
        f"{len(artifact_files)} source-map artifacts"
    )


if __name__ == "__main__":
    main()

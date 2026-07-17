import argparse
import json
import re
from os import environ
from pathlib import Path
from sys import argv

ASSIGNMENT = re.compile(r"^(?:#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")


def materialize_env(
    template: Path,
    output: Path,
    *,
    names: tuple[str, ...] = (),
    prefixes: tuple[str, ...] = (),
) -> None:
    values: list[str] = []
    for line in template.read_text().splitlines():
        match = ASSIGNMENT.fullmatch(line)
        if match is None:
            continue
        name, template_value = match.groups()
        if names or prefixes:
            if name not in names and not name.startswith(prefixes):
                continue
        if name in environ:
            values.append(f"{name}={json.dumps(environ[name])}")
        elif not line.startswith("#"):
            values.append(f"{name}={template_value}")
    output.write_text("\n".join(values) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--template", type=Path, default=Path(".env.example"))
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--prefix", action="append", default=[])
    args = parser.parse_args(argv[1:])
    materialize_env(
        args.template,
        args.output,
        names=tuple(args.name),
        prefixes=tuple(args.prefix),
    )


if __name__ == "__main__":
    main()

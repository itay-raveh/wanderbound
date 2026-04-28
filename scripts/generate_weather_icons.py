import ast
from pathlib import Path

from lib.downloads import (
    download_atomic,
    download_many,
    remove_partial_downloads,
    write_manifest,
)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "https://basmilius.github.io/meteocons/production/fill/svg/{name}.svg"
MAX_WORKERS = 8


def weather_icon_names() -> list[str]:
    source_path = ROOT / "backend" / "app" / "services" / "open_meteo.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names: set[str] = {"not-available"}
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_WMO_ICONS"
        ):
            mapping = ast.literal_eval(node.value)
            names.update(mapping.values())
    names.update(name.replace("-day", "-night") for name in list(names))
    return sorted(names)


def download(name: str, output_dir: Path) -> None:
    url = SOURCE.format(name=name)
    download_atomic(url, output_dir / f"{name}.svg", validate=validate_svg)


def validate_svg(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "<svg" in text:
        if not text.endswith("\n"):
            path.write_text(text + "\n", encoding="utf-8")
        return
    msg = f"Downloaded invalid weather icon: {path}"
    raise RuntimeError(msg)


def main() -> None:
    output_dir = ROOT / "frontend" / "public" / "weather-icons"
    output_dir.mkdir(parents=True, exist_ok=True)
    remove_partial_downloads(output_dir)
    for tmp_path in output_dir.glob("tmp*.svg"):
        tmp_path.unlink()
    names = weather_icon_names()
    download_many(
        names, lambda name: download(name, output_dir), max_workers=MAX_WORKERS
    )
    write_manifest(output_dir, source=SOURCE, files=[f"{name}.svg" for name in names])
    print(f"Generated {len(names)} weather SVGs in {output_dir}")


if __name__ == "__main__":
    main()

import ast
import json
import shutil
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
    target = output_dir / f"{name}.svg"
    with tempfile.NamedTemporaryFile(
        dir=output_dir, prefix=".download-", suffix=".tmp", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            with tmp_path.open("wb") as f:
                shutil.copyfileobj(response, f)
        text = tmp_path.read_text(encoding="utf-8")
        if "<svg" not in text:
            msg = f"Downloaded invalid weather icon: {url}"
            raise RuntimeError(msg)
        tmp_path.replace(target)
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> None:
    output_dir = ROOT / "frontend" / "public" / "weather-icons"
    output_dir.mkdir(parents=True, exist_ok=True)
    for tmp_path in output_dir.glob(".download-*.tmp"):
        tmp_path.unlink()
    for tmp_path in output_dir.glob("tmp*.svg"):
        tmp_path.unlink()
    names = weather_icon_names()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(executor.map(lambda name: download(name, output_dir), names))
    manifest = {
        "source": SOURCE,
        "files": [f"{name}.svg" for name in names],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Generated {len(names)} weather SVGs in {output_dir}")


if __name__ == "__main__":
    main()

import json
from pathlib import Path

from lib.downloads import (
    download_atomic,
    download_many,
    remove_partial_downloads,
    write_manifest,
)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "https://flagcdn.com/w160/{code}.png"
MAX_WORKERS = 16


def country_codes() -> list[str]:
    data_path = ROOT / "backend" / "app" / "logic" / "country_colors.json"
    countries = json.loads(data_path.read_text(encoding="utf-8"))
    return sorted(
        country["code"].lower() for country in countries if country["code"] != "00"
    )


def download(code: str, output_dir: Path) -> None:
    url = SOURCE.format(code=code)
    download_atomic(url, output_dir / f"{code}.png")


def main() -> None:
    output_dir = ROOT / "frontend" / "public" / "flags"
    output_dir.mkdir(parents=True, exist_ok=True)
    remove_partial_downloads(output_dir)
    codes = country_codes()
    download_many(
        codes, lambda code: download(code, output_dir), max_workers=MAX_WORKERS
    )
    write_manifest(output_dir, source=SOURCE, files=[f"{code}.png" for code in codes])
    print(f"Generated {len(codes)} flag PNGs in {output_dir}")


if __name__ == "__main__":
    main()

import json
import shutil
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
    target = output_dir / f"{code}.png"
    with tempfile.NamedTemporaryFile(
        dir=output_dir, prefix=".download-", suffix=".tmp", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            with tmp_path.open("wb") as f:
                shutil.copyfileobj(response, f)
        if tmp_path.stat().st_size == 0:
            msg = f"Downloaded empty flag: {url}"
            raise RuntimeError(msg)
        tmp_path.replace(target)
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> None:
    output_dir = ROOT / "frontend" / "public" / "flags"
    output_dir.mkdir(parents=True, exist_ok=True)
    for tmp_path in output_dir.glob(".download-*.tmp"):
        tmp_path.unlink()
    codes = country_codes()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(executor.map(lambda code: download(code, output_dir), codes))
    manifest = {
        "source": SOURCE,
        "files": [f"{code}.png" for code in codes],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Generated {len(codes)} flag PNGs in {output_dir}")


if __name__ == "__main__":
    main()

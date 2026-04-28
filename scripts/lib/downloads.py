import json
import shutil
import tempfile
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def download_atomic(
    url: str,
    target: Path,
    *,
    timeout: int = 30,
    validate: Callable[[Path], None] | None = None,
    skip_existing: bool = False,
) -> None:
    if skip_existing and target.exists() and target.stat().st_size > 0:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=target.parent, prefix=".download-", suffix=".tmp", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            with tmp_path.open("wb") as f:
                shutil.copyfileobj(response, f)
        if tmp_path.stat().st_size == 0:
            msg = f"Downloaded empty file: {url}"
            raise RuntimeError(msg)
        if validate:
            validate(tmp_path)
        tmp_path.replace(target)
        target.chmod(0o644)
    finally:
        tmp_path.unlink(missing_ok=True)


def download_many(
    items: Iterable[str],
    download: Callable[[str], None],
    *,
    max_workers: int,
) -> None:
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(download, items))


def remove_partial_downloads(output_dir: Path) -> None:
    for tmp_path in output_dir.glob(".download-*.tmp"):
        tmp_path.unlink()


def write_manifest(output_dir: Path, *, source: str, files: list[str]) -> None:
    manifest = {"source": source, "files": files}
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

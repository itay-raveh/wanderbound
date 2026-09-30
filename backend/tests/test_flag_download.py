from importlib import import_module
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.error import URLError

if TYPE_CHECKING:
    import pytest


def test_flag_download_retries_and_reuses_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    downloads = import_module("lib.downloads")
    flags = import_module("generate_flags")
    calls = 0

    def fake_urlopen(_url: str, **_kwargs: object) -> BytesIO:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError("connection closed")
        return BytesIO(f"flag{calls}".encode())

    monkeypatch.setattr(downloads.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(downloads.time, "sleep", lambda _: None)

    flags.download("ad", tmp_path)
    assert (tmp_path / "ad.png").read_bytes() == b"flag2"
    flags.download("ad", tmp_path)
    assert calls == 2
    flags.download("ad", tmp_path, refresh=True)
    assert (tmp_path / "ad.png").read_bytes() == b"flag3"

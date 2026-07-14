import shutil
from contextlib import suppress
from pathlib import Path


def remove_tree_if_present(path: Path) -> None:
    with suppress(FileNotFoundError):
        shutil.rmtree(path)

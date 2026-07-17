import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest


def _load_materialize_env() -> Any:
    script = Path(__file__).parents[2] / "scripts" / "materialize_env.py"
    spec = importlib.util.spec_from_file_location("materialize_env", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.materialize_env


def test_materialize_env_uses_process_values_and_keeps_template_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = tmp_path / "example"
    output = tmp_path / "output"
    template.write_text("REQUIRED=\nDEFAULTED=from-template\n# OPTIONAL=\n")
    monkeypatch.setenv("REQUIRED", "from environment")
    monkeypatch.setenv("OPTIONAL", "quoted\nvalue")

    _load_materialize_env()(template, output)

    assert output.read_text().splitlines() == [
        'REQUIRED="from environment"',
        "DEFAULTED=from-template",
        'OPTIONAL="quoted\\nvalue"',
    ]


def test_materialize_env_can_select_names_and_prefixes(tmp_path: Path) -> None:
    template = tmp_path / "example"
    output = tmp_path / "output"
    template.write_text("MODE=local\nPUBLIC_ONE=one\nPRIVATE_ONE=secret\n")

    _load_materialize_env()(
        template,
        output,
        names=("MODE",),
        prefixes=("PUBLIC_",),
    )

    assert output.read_text().splitlines() == ["MODE=local", "PUBLIC_ONE=one"]

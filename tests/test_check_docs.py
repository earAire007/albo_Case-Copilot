"""Spec 01b — AC6: verificación determinista de coherencia de documentos."""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_docs.py"


def _check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True
    )


def _copy_docs(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copy(REPO_ROOT / "DESIGN.md", root / "DESIGN.md")
    shutil.copytree(REPO_ROOT / "specs", root / "specs")
    shutil.copytree(
        REPO_ROOT / "tests", root / "tests", ignore=shutil.ignore_patterns("__pycache__")
    )
    return root


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_check_docs_passes_on_repo():
    result = _check(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_docs_passes_on_copy(tmp_path):
    assert _check(_copy_docs(tmp_path)).returncode == 0


def test_fails_on_nonexistent_test_in_design(tmp_path):
    root = _copy_docs(tmp_path)
    _edit(
        root / "DESIGN.md",
        "| 1 | Sin capacidad de mover dinero | <!-- --> |",
        "| 1 | Sin capacidad de mover dinero | `test_does_not_exist` |",
    )
    result = _check(root)
    assert result.returncode != 0
    assert "test_does_not_exist" in result.stdout


def test_pending_test_in_design_is_allowed(tmp_path):
    root = _copy_docs(tmp_path)
    _edit(
        root / "DESIGN.md",
        "| 1 | Sin capacidad de mover dinero | <!-- --> |",
        "| 1 | Sin capacidad de mover dinero | `test_future` (pendiente, spec 02) |",
    )
    assert _check(root).returncode == 0


def test_fails_on_broken_readme_link(tmp_path):
    root = _copy_docs(tmp_path)
    (root / "specs" / "01b-harness-desarrollo.md").unlink()
    result = _check(root)
    assert result.returncode != 0
    assert "01b-harness-desarrollo.md" in result.stdout


def test_fails_on_spec_without_row(tmp_path):
    root = _copy_docs(tmp_path)
    readme = root / "specs" / "README.md"
    lines = [ln for ln in readme.read_text().splitlines() if "01b-harness-desarrollo.md" not in ln]
    readme.write_text("\n".join(lines) + "\n")
    result = _check(root)
    assert result.returncode != 0
    assert "01b-harness-desarrollo.md" in result.stdout


def test_fails_on_status_mismatch(tmp_path):
    root = _copy_docs(tmp_path)
    _edit(root / "specs" / "01-dominio-dataset.md", "**Estado:** cerrada", "**Estado:** activa")
    result = _check(root)
    assert result.returncode != 0
    assert "01-dominio-dataset.md" in result.stdout

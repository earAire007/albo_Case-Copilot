"""Spec 01b — AC1, AC4: pyright y contratos de import-linter."""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN = Path(sys.executable).parent


def _pyright(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BIN / "pyright"), "--project", str(REPO_ROOT / "pyproject.toml"), str(target)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_pyright_flags_type_error(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text('amount: int = "cien"\n')
    result = _pyright(bad)
    assert result.returncode != 0
    assert "1 error" in result.stdout


def test_pyright_accepts_well_typed_file(tmp_path):
    good = tmp_path / "good.py"
    good.write_text("amount: int = 100\n")
    assert _pyright(good).returncode == 0


def test_make_check_runs_lint_test_check_docs_in_order():
    result = subprocess.run(
        ["make", "-n", "check"], capture_output=True, text=True, cwd=REPO_ROOT, check=True
    )
    out = result.stdout
    steps = ["ruff check", "pyright", "lint-imports", "pytest", "check_docs.py"]
    positions = [out.find(step) for step in steps]
    assert -1 not in positions, out
    assert positions == sorted(positions), out


def _lint_imports(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(BIN / "lint-imports")], capture_output=True, text=True, cwd=root)


def _copy_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(
        REPO_ROOT / "backend", root / "backend", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy(REPO_ROOT / "pyproject.toml", root / "pyproject.toml")
    return root


def test_import_contracts_pass(tmp_path):
    result = _lint_imports(_copy_project(tmp_path))
    assert result.returncode == 0, result.stdout


def test_forbidden_import_breaks_contracts(tmp_path):
    root = _copy_project(tmp_path)
    models = root / "backend" / "domain" / "models.py"
    models.write_text(models.read_text() + "\nimport fastapi  # noqa\n")
    result = _lint_imports(root)
    assert result.returncode != 0
    assert "domain is framework-free BROKEN" in result.stdout


def test_layer_violation_breaks_contracts(tmp_path):
    root = _copy_project(tmp_path)
    repo_module = root / "backend" / "mock_core" / "repository.py"
    repo_module.write_text(repo_module.read_text() + "\nimport backend.mock_core.api  # noqa\n")
    result = _lint_imports(root)
    assert result.returncode != 0
    assert "mock_core layers" in result.stdout and "BROKEN" in result.stdout

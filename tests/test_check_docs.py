"""Spec 01b — AC6: verificación determinista de coherencia de documentos.

Runs against a synthetic repo in tmp so the tests don't depend on the live content
of DESIGN.md or specs/ (which evolves spec by spec); one test checks the real repo.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_docs.py"

README = """\
| # | Spec | Estado | Tiempo |
|---|------|--------|--------|
| 01 | [Uno](01-uno.md) | cerrada | 1 h |
| 02 | [Dos](02-dos.md) | borrador | 1 h |
| 03 | Tres | pendiente | 1 h |
"""

DESIGN = """\
## Modelo de defensa

| # | Invariante | Test |
|---|------------|------|
| 1 | Completa | `test_real` |
| 2 | Parcial con pendiente | `test_real` (parcial: mock); `test_future` (pendiente, spec 02) |
| 3 | Solo pendiente | `test_x[a\\|b]` (pendiente, specs 02 y 03) |
| 4 | Contrato pendiente | contrato `a no importa b` (pendiente, spec 02) |
"""


def _check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True
    )


def _repo(tmp_path: Path, design: str = DESIGN, readme: str = README) -> Path:
    root = tmp_path / "repo"
    (root / "specs").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "DESIGN.md").write_text(design, encoding="utf-8")
    (root / "specs" / "README.md").write_text(readme, encoding="utf-8")
    (root / "specs" / "01-uno.md").write_text("# Uno\n\n**Estado:** cerrada\n", encoding="utf-8")
    (root / "specs" / "02-dos.md").write_text("# Dos\n\n**Estado:** borrador\n", encoding="utf-8")
    (root / "specs" / "_template.md").write_text("**Estado:** borrador\n", encoding="utf-8")
    (root / "tests" / "test_sample.py").write_text("def test_real():\n    pass\n")
    return root


def _with_row(row: str) -> str:
    return DESIGN + row + "\n"


def _fails_with(tmp_path: Path, needle: str, **kwargs: str) -> None:
    result = _check(_repo(tmp_path, **kwargs))
    assert result.returncode != 0
    assert needle in result.stdout, result.stdout


def test_check_docs_passes_on_repo():
    result = _check(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_synthetic_repo_passes(tmp_path):
    result = _check(_repo(tmp_path))
    assert result.returncode == 0, result.stdout


def test_fails_on_nonexistent_test_in_design(tmp_path):
    _fails_with(
        tmp_path, "test_does_not_exist", design=_with_row("| 5 | X | `test_does_not_exist` |")
    )


def test_fails_on_row_without_tests_or_pending(tmp_path):
    _fails_with(
        tmp_path, "invariante 5: sin tests ni pendientes", design=_with_row("| 5 | X | <!-- --> |")
    )


def test_fails_on_partial_only_row(tmp_path):
    _fails_with(
        tmp_path,
        "invariante 5: solo cobertura parcial",
        design=_with_row("| 5 | X | `test_real` (parcial: logs) |"),
    )


def test_fails_on_pending_owned_by_closed_spec(tmp_path):
    _fails_with(
        tmp_path,
        "spec 01 está cerrada",
        design=_with_row("| 5 | X | `test_future` (pendiente, spec 01) |"),
    )


def test_pending_shared_with_open_spec_is_allowed(tmp_path):
    design = _with_row("| 5 | X | `test_future` (pendiente, specs 01 y 02) |")
    assert _check(_repo(tmp_path, design=design)).returncode == 0


def test_only_the_invariants_table_is_checked(tmp_path):
    """Other tables whose first cell is a number (e.g. time per spec) are not invariants."""
    time_table = "| Spec | Estimado |\n|---|---|\n| 00 | 20 min | x |\n"
    design = DESIGN + "\nTexto.\n\n## Tiempo\n\n" + time_table
    result = _check(_repo(tmp_path, design=design))
    assert result.returncode == 0, result.stdout


def test_rows_after_the_invariants_table_are_ignored(tmp_path):
    """The invariants table ends at the first non-table line, even inside its section."""
    design = DESIGN + "\n### Riesgo residual\n\n| 9 | X | sin tests |\n"
    assert _check(_repo(tmp_path, design=design)).returncode == 0


def test_fails_without_invariants_section(tmp_path):
    design = DESIGN.replace("## Modelo de defensa", "## Otra cosa")
    _fails_with(tmp_path, "sin tabla de invariantes", design=design)


def test_fails_on_broken_readme_link(tmp_path):
    root = _repo(tmp_path)
    (root / "specs" / "02-dos.md").unlink()
    result = _check(root)
    assert result.returncode != 0
    assert "02-dos.md" in result.stdout


def test_fails_on_spec_without_row(tmp_path):
    root = _repo(tmp_path)
    (root / "specs" / "04-cuatro.md").write_text("**Estado:** borrador\n", encoding="utf-8")
    result = _check(root)
    assert result.returncode != 0
    assert "04-cuatro.md no tiene fila" in result.stdout


def test_fails_on_status_mismatch(tmp_path):
    _fails_with(tmp_path, "01-uno.md", readme=README.replace("| cerrada |", "| activa |"))

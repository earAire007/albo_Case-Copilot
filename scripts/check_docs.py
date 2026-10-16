"""Deterministic doc-coherence checks (spec 01b). Used by `make check-docs` and /check-docs.

DESIGN.md invariants table — the third cell lists coverage items separated by ";":
    `test_name` | `test_name[a\\|b]`      a test that must exist in tests/
    contrato `name`                       an import-linter contract
    ... (parcial: <qué cubre>)            covers only part of the invariant
    ... (pendiente, spec NN[ y MM])       not written yet; owned by those specs

Rules:
1. Every named test without a pending mark exists in tests/.
2. A row with no tests and no pending items is an error.
3. A row whose tests are all partial and has no pending item is an error.
4. A pending mark whose specs are all closed in specs/README.md is an error.
5. Every specs/README.md row link points to an existing spec, every spec file has a
   row, and the row status matches the spec's **Estado:** line.

Semantic coherence (spec 00 <-> DESIGN.md) is left to the /check-docs command.
"""

import argparse
import re
import sys
from pathlib import Path

CELL_SPLIT = re.compile(r"(?<!\\)\|")
TEST_NAME = re.compile(r"`(test_\w+)")
TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)", re.MULTILINE)
PENDING = re.compile(r"\(pendiente,\s*specs?\s+([^)]+)\)", re.IGNORECASE)
PARTIAL = re.compile(r"\(parcial\b", re.IGNORECASE)
SPEC_ID = re.compile(r"\b(\d{2}[a-z]?)\b")
LINK = re.compile(r"\]\(([^)]+\.md)\)")
STATUS_LINE = re.compile(r"^\*\*Estado:\*\*\s*(.+?)\s*$", re.MULTILINE)
NON_SPEC_FILES = {"README.md", "_template.md"}
CLOSED = "cerrada"


def table_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if line.startswith("|"):
            rows.append([c.strip() for c in CELL_SPLIT.split(line.strip().strip("|"))])
    return rows


def defined_tests(tests_dir: Path) -> set[str]:
    names: set[str] = set()
    for path in sorted(tests_dir.rglob("*.py")):
        names.update(TEST_DEF.findall(path.read_text(encoding="utf-8")))
    return names


def spec_statuses(root: Path) -> dict[str, str]:
    """Spec id (e.g. '01b') -> status column in specs/README.md."""
    statuses = {}
    for cells in table_rows((root / "specs" / "README.md").read_text(encoding="utf-8")):
        if len(cells) >= 3 and SPEC_ID.fullmatch(cells[0]):
            statuses[cells[0]] = cells[2]
    return statuses


def check_design(root: Path) -> list[str]:
    errors: list[str] = []
    existing = defined_tests(root / "tests")
    statuses = spec_statuses(root)
    for cells in table_rows((root / "DESIGN.md").read_text(encoding="utf-8")):
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        where = f"DESIGN.md invariante {cells[0]}"
        items = [i.strip() for i in cells[2].split(";") if i.strip() and "<!--" not in i]
        has_pending = False
        test_items = []
        for item in items:
            pending = PENDING.search(item)
            if pending:
                has_pending = True
                ids = SPEC_ID.findall(pending.group(1))
                if ids and all(statuses.get(i) == CLOSED for i in ids):
                    errors.append(
                        f"{where}: '{item}' sigue pendiente pero spec {', '.join(ids)} está cerrada"
                    )
                continue
            for name in TEST_NAME.findall(item):
                test_items.append(item)
                if name not in existing:
                    errors.append(
                        f"{where}: `{name}` no existe en tests/ y no está marcado como pendiente"
                    )
        if not test_items and not has_pending:
            errors.append(f"{where}: sin tests ni pendientes")
        elif test_items and all(PARTIAL.search(i) for i in test_items) and not has_pending:
            errors.append(f"{where}: solo cobertura parcial y ningún pendiente que la complete")
    return errors


def check_specs_index(root: Path) -> list[str]:
    errors: list[str] = []
    specs = root / "specs"
    linked: set[str] = set()
    for cells in table_rows((specs / "README.md").read_text(encoding="utf-8")):
        if len(cells) < 3:
            continue
        link = LINK.search(cells[1])
        if not link:
            continue
        filename, row_status = link.group(1), cells[2]
        linked.add(filename)
        spec_path = specs / filename
        if not spec_path.is_file():
            errors.append(f"specs/README.md enlaza a {filename}, que no existe")
            continue
        status = STATUS_LINE.search(spec_path.read_text(encoding="utf-8"))
        file_status = status.group(1).strip() if status else "(sin **Estado:**)"
        if file_status != row_status:
            errors.append(
                f"{filename}: estado '{file_status}' no coincide con specs/README.md "
                f"('{row_status}')"
            )
    for spec_path in sorted(specs.glob("*.md")):
        if spec_path.name not in NON_SPEC_FILES and spec_path.name not in linked:
            errors.append(f"{spec_path.name} no tiene fila en specs/README.md")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    errors = check_design(args.root) + check_specs_index(args.root)
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"\ncheck-docs: {len(errors)} inconsistencia(s).")
        return 1
    print("check-docs: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

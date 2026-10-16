"""Deterministic doc-coherence checks (spec 01b). Used by `make check-docs` and /check-docs.

1. Every test named in the DESIGN.md invariants table exists in tests/ or is marked
   "pendiente".
2. Every specs/README.md row link points to an existing spec, every spec file has a
   row, and the row status matches the spec's **Estado:** line.

Semantic coherence (spec 00 <-> DESIGN.md) is left to the /check-docs command.
"""

import argparse
import re
import sys
from pathlib import Path

INVARIANT_ROW = re.compile(r"^\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|\s*$")
TEST_NAME = re.compile(r"`(test_\w+)`")
TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)", re.MULTILINE)
README_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|([^|]*)\|\s*([^|]+?)\s*\|")
LINK = re.compile(r"\]\(([^)]+\.md)\)")
STATUS_LINE = re.compile(r"^\*\*Estado:\*\*\s*(.+?)\s*$", re.MULTILINE)
NON_SPEC_FILES = {"README.md", "_template.md"}


def defined_tests(tests_dir: Path) -> set[str]:
    names: set[str] = set()
    for path in sorted(tests_dir.rglob("*.py")):
        names.update(TEST_DEF.findall(path.read_text(encoding="utf-8")))
    return names


def check_design(root: Path) -> list[str]:
    errors: list[str] = []
    existing = defined_tests(root / "tests")
    for line in (root / "DESIGN.md").read_text(encoding="utf-8").splitlines():
        m = INVARIANT_ROW.match(line)
        if not m:
            continue
        number, cell = m.group(1), m.group(3)
        if "pendiente" in cell.lower():
            continue
        for name in TEST_NAME.findall(cell):
            if name not in existing:
                errors.append(
                    f"DESIGN.md invariante {number}: `{name}` no existe en tests/ "
                    "y no está marcado como pendiente"
                )
    return errors


def check_specs_index(root: Path) -> list[str]:
    errors: list[str] = []
    specs = root / "specs"
    linked: set[str] = set()
    for line in (specs / "README.md").read_text(encoding="utf-8").splitlines():
        m = README_ROW.match(line)
        if not m:
            continue
        link = LINK.search(m.group(2))
        if not link:
            continue
        filename, row_status = link.group(1), m.group(3).strip()
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

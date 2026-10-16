"""Spec 01b — AC5: hooks de Claude Code registrados y con el contrato de salida correcto."""

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / ".claude" / "hooks"


def _run(script: str, payload: dict, env: dict[str, str] | None = None):
    return subprocess.run(
        ["bash", str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        cwd=REPO_ROOT,
    )


def test_hooks_registered():
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    hooks = settings["hooks"]
    post = [
        h["command"]
        for entry in hooks["PostToolUse"]
        if {"Edit", "Write"} <= set(entry["matcher"].split("|"))
        for h in entry["hooks"]
    ]
    assert any("ruff-on-edit.sh" in cmd for cmd in post)
    stop = [h["command"] for entry in hooks["Stop"] for h in entry["hooks"]]
    assert any("verify-on-stop.sh" in cmd for cmd in stop)


def test_ruff_hook_skips_non_python(tmp_path):
    doc = tmp_path / "notes.md"
    doc.write_text("import os\n")
    assert _run("ruff-on-edit.sh", {"tool_input": {"file_path": str(doc)}}).returncode == 0


def test_ruff_hook_blocks_bad_python(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import os\n")
    result = _run("ruff-on-edit.sh", {"tool_input": {"file_path": str(bad)}})
    assert result.returncode == 2
    assert "F401" in result.stderr


def test_ruff_hook_accepts_clean_python(tmp_path):
    good = tmp_path / "good.py"
    good.write_text('print("ok")\n')
    assert _run("ruff-on-edit.sh", {"tool_input": {"file_path": str(good)}}).returncode == 0


def test_stop_hook_blocks_on_failure():
    result = _run("verify-on-stop.sh", {"stop_hook_active": False}, {"VERIFY_ON_STOP_CMD": "false"})
    assert result.returncode == 2
    assert result.stderr


def test_stop_hook_passes_when_green():
    result = _run("verify-on-stop.sh", {"stop_hook_active": False}, {"VERIFY_ON_STOP_CMD": "true"})
    assert result.returncode == 0


def test_stop_hook_does_not_loop():
    result = _run("verify-on-stop.sh", {"stop_hook_active": True}, {"VERIFY_ON_STOP_CMD": "false"})
    assert result.returncode == 0
    assert result.stderr, "debe reportar la falla aunque no bloquee"

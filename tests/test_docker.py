"""Spec 08 — la imagen nunca recibe secretos, la base local ni el enunciado confidencial."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_dockerignore_excludes_secrets():
    path = REPO_ROOT / ".dockerignore"
    assert path.exists(), "docker compose up copia el repo: sin .dockerignore entra todo"
    lines = {line.strip() for line in path.read_text().splitlines()}
    for pattern in (".env", ".env.*", "var/", ".local/"):
        assert pattern in lines, pattern
    assert "!.env" not in lines

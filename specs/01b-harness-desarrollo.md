# Spec 01b — Harness de desarrollo

**Estado:** borrador
**Depende de:** spec-01

## Objetivo

Que las reglas no negociables se verifiquen con sensores automáticos durante el desarrollo, no solo por escrito, antes de construir la frontera de seguridad (spec 02).

## Fuera de alcance

- CI y pre-commit de git.
- Enmascarado real: `mask()` es de la spec 02; aquí solo se **detecta**.
- Reglas para el frontend (spec 07).

## Contratos

- **`make lint`** = `ruff check` + `ruff format --check` + `pyright` (modo `standard` sobre `backend/`, `data/` y `tests/`) + `lint-imports`.
- **Hook de Claude Code** (`.claude/settings.json`, `PostToolUse`, matcher `Edit|Write`): ejecuta `.claude/hooks/lint-on-edit.sh`, que lee `tool_input.file_path` del JSON de stdin, ignora lo que no sea `.py` y corre `make lint`. Si falla, sale con código 2 para que la salida le llegue al agente como feedback.
- **Detector** `backend/domain/sensitive.py`: `find_sensitive(text) -> list[Finding]` (tipo y posición, nunca el valor). Detecta CLABE (18 dígitos con dígito verificador válido), PAN (13–19 dígitos que pasan Luhn), RFC y CURP. Reutiliza `clabe_is_valid`, `luhn_is_valid`, `RFC_RE` y `CURP_RE` de `backend/domain/validators.py`. La spec 02 lo reutiliza para revisar trazas.
- **Fixture global** (autouse, en `tests/conftest.py`): agrega un handler al root logger durante cada test y, al terminar, hace fallar el test si `find_sensitive` encuentra algo en algún registro (mensaje formateado + `exc_text`). Sin marcador de excepción.
- **`/check-docs`** (`.claude/commands/check-docs.md`): corre `make check-docs` (`scripts/check_docs.py`, determinista), interpreta el reporte y propone correcciones sin editar nada. El script verifica:
  1. cada invariante numerada de la spec 00 aparece en la tabla de `DESIGN.md` con el mismo número;
  2. cada test nombrado en esa tabla existe como `def test_…` en `tests/` o está marcado "pendiente, spec NN";
  3. el estado de cada spec en `specs/README.md` coincide con su línea `**Estado:**`.

## Contratos de arquitectura

`[tool.importlinter]` en `pyproject.toml`, `root_package = backend`. Solo módulos existentes:

1. Capas: `backend.mock_core.api` → `backend.mock_core.repository` → `backend.domain`.
2. `backend.domain` no importa `fastapi`, `uvicorn` ni `backend.mock_core`.

## Criterios de aceptación

1. `make lint` pasa sobre el código actual y falla ante un error de tipos introducido (test con archivo temporal).
2. Un test con `pytester` demuestra que el fixture hace fallar un test que loguea una CLABE, una tarjeta, un RFC o una CURP completos, y que no falla con formas enmascaradas (`****1234`) ni con 18 dígitos sin dígito verificador válido.
3. `find_sensitive` detecta todos los identificadores de `data/customers.json` (sin falsos negativos sobre el dataset).
4. `lint-imports` pasa; un import prohibido (`backend.domain` → `fastapi`) lo hace fallar.
5. El hook está registrado en `.claude/settings.json`; el script sale con 0 para archivos que no son `.py` y con 2 cuando `make lint` falla (subprocess con un JSON de stdin simulado).
6. `make check-docs` pasa sobre el repo actual y falla si se borra una fila de la tabla de invariantes o se nombra un test inexistente (fixtures temporales).

## Riesgos y decisiones abiertas

- **Pyright o mypy.** Propuesta: pyright, porque es más rápido en el hook y tiene buen soporte de Pydantic v2.
- **`/check-docs` solo como prompt o respaldado por un script.** Propuesta: script, para que sea un sensor computacional y no otra instrucción al LLM.
- **Costo del hook:** `make lint` completo en cada edición (~2–4 s). Si estorba, se acota a ruff sobre el archivo editado y se dejan pyright e import-linter para `make lint`.
- **Falsos positivos del detector:** números largos (claves de rastreo, ids). Mitigación: exigir dígito verificador o Luhn. Riesgo residual: un número al azar que pase el checksum (~10 %); se acepta, porque es preferible fallar de más.
- **Límite del fixture:** solo cubre `logging`, no `print` ni trazas. Las trazas se cubren en la spec 05 con el mismo detector.

## Cambios durante la implementación

<!-- Se llena al cerrar. -->

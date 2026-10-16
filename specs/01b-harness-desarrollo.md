# Spec 01b — Harness de desarrollo

**Estado:** borrador
**Depende de:** spec-01

## Objetivo

Que las reglas no negociables se verifiquen con sensores automáticos durante el desarrollo, no solo por escrito, antes de construir la frontera de seguridad (spec 02).

## Fuera de alcance

- CI y pre-commit de git, por tiempo: con 6–8 h, el presupuesto va a seguridad y evals. Sustituto: `make check` como regla de `AGENTS.md` antes de cada commit, válida para cualquier agente o persona. Riesgo residual (documentado en DESIGN.md): la regla se puede saltar; nada bloquea un commit en rojo fuera de Claude Code.
- Enmascarado real: `mask()` es de la spec 02; aquí solo se **detecta**.
- Reglas para el frontend (spec 07).

## Contratos

- **`make check`** = `make lint` → `make test` → `make check-docs`, en ese orden. Es el único punto de verificación que no depende de la herramienta del agente.
- **`make lint`** = `ruff check` + `ruff format --check` + `pyright` + `lint-imports`. Pyright en modo `standard` sobre `backend/`, `data/` y `tests/`, y en `strict` (lista `strict` de `[tool.pyright]`) sobre los módulos críticos (enmascarado, gate de aprobación, validador, executor) a medida que existan. Hoy la lista está vacía y cada spec que cree uno lo agrega.
- **Hooks de Claude Code** (`.claude/settings.json`), en dos niveles:
  - `PostToolUse`, matcher `Edit|Write` → `.claude/hooks/ruff-on-edit.sh`: lee `tool_input.file_path` del JSON de stdin; si es `.py`, corre `ruff check` y `ruff format --check` solo sobre ese archivo; si falla, sale con 2 (feedback al agente). Si no es `.py`, sale con 0.
  - `Stop` → `.claude/hooks/verify-on-stop.sh`: corre `$VERIFY_ON_STOP_CMD` (por defecto `make lint && make test`; la variable existe para que los tests inyecten el comando sin recursión); si falla, sale con 2 y el agente recibe la salida y sigue trabajando. **Anti-bucle:** si el input trae `stop_hook_active: true` (ya se bloqueó una vez en este ciclo), reporta la falla en stderr y sale con 0 para no encerrar al agente.
- **Detector** `backend/domain/sensitive.py`: `find_sensitive(text) -> list[Finding]` (tipo y posición, nunca el valor). Detecta CLABE (18 dígitos con dígito verificador válido), PAN (13–19 dígitos que pasan Luhn), RFC y CURP. Reutiliza `clabe_is_valid`, `luhn_is_valid`, `RFC_RE` y `CURP_RE` de `backend/domain/validators.py`. La spec 02 lo reutiliza para revisar trazas.
- **Sensor de fugas en tests** (plugin `tests/sensitive_logs.py` registrado en `tests/conftest.py` vía `pytest_plugins`, para poder probarlo con `pytester`). Sin marcador de excepción.
  - **Logs:** fixture autouse que agrega un handler al root logger y baja su nivel a `DEBUG` durante cada test (luego lo restaura); al terminar, falla si `find_sensitive` encuentra algo en algún registro (mensaje formateado + `exc_text`).
  - **stdout, stderr y excepciones:** hookwrapper `pytest_runtest_makereport` que revisa las secciones capturadas y el `longrepr` de cada fase, y marca el reporte como fallido. No pide `capsys`/`capfd`, así que no choca con los tests que los usan.
  - **Puntos ciegos:** salida que el propio test consume con `capsys.readouterr()` (el test se hace dueño de ella), corridas con `-s`, y excepciones atrapadas que nunca se imprimen ni se loguean.
- **`/check-docs`** (`.claude/commands/check-docs.md`), híbrido; no edita nada, reporta y propone correcciones:
  - **Determinista:** `scripts/check_docs.py` (`make check-docs`, código ≠ 0 si falla) verifica que:
    1. cada test nombrado en la tabla de invariantes de `DESIGN.md` exista como `def test_…` en `tests/` o esté marcado "pendiente, spec NN";
    2. cada fila de `specs/README.md` enlace a un archivo existente en `specs/`, cada `specs/NN*-*.md` tenga su fila, y el estado de la fila coincida con la línea `**Estado:**` de la spec.
  - **Semántico:** después del script, el comando revisa la coherencia entre las invariantes de la spec 00 y la tabla de `DESIGN.md` (que el número, el nombre y el alcance coincidan, y que el test nombrado cubra lo que dice la invariante).

## Contratos de arquitectura

`[tool.importlinter]` en `pyproject.toml`, `root_package = backend`. Solo módulos existentes:

1. Capas: `backend.mock_core.api` → `backend.mock_core.repository` → `backend.domain`.
2. `backend.domain` no importa `fastapi`, `uvicorn` ni `backend.mock_core`.

## Criterios de aceptación

1. `make lint` pasa sobre el código actual (lo verifica el hook `Stop` en cada turno), y un test demuestra que pyright, con la configuración del repo, falla ante un error de tipos en un archivo temporal.
2. Un test con `pytester` (`runpytest_subprocess`, para que el fixture externo no capture los logs de la sesión interna) demuestra que el fixture hace fallar un test que loguea una CLABE, una tarjeta, un RFC o una CURP completos, y que no falla con formas enmascaradas (`****1234`) ni con 18 dígitos sin dígito verificador válido.
3. `find_sensitive` detecta todos los identificadores de `data/customers.json` (sin falsos negativos sobre el dataset).
4. `lint-imports` pasa; un import prohibido (`backend.domain` → `fastapi`) lo hace fallar.
5. Ambos hooks están registrados en `.claude/settings.json`. Con subprocess y un JSON de stdin simulado se verifica:
   - `ruff-on-edit.sh` sale con 0 para archivos que no son `.py` y con 2 para un `.py` con error de ruff;
   - `verify-on-stop.sh` sale con 2 si `make lint` o `make test` fallan y con 0 si `stop_hook_active` es `true`.
6. `make check-docs` pasa sobre el repo actual y falla, con fixtures temporales, si la tabla de `DESIGN.md` nombra un test inexistente no marcado como pendiente, si una fila de `specs/README.md` enlaza a un archivo inexistente, si falta la fila de una spec o si los estados no coinciden.
7. `make check` corre lint, test y check-docs en ese orden (`test_make_check_runs_lint_test_check_docs_in_order`, vía `make -n`).

## Riesgos y decisiones abiertas

Resueltas:

- **Pyright, no mypy.** Modo `standard` en general y `strict` en los módulos críticos (enmascarado, gate de aprobación, validador, executor) a medida que existan. Razón: velocidad en el ciclo del hook y buen soporte de Pydantic v2 sin plugins.
- **`/check-docs` híbrido.** El script cubre lo determinista (tests de la tabla de invariantes, filas de `specs/README.md` contra archivos en `specs/`); el comando agrega la revisión semántica spec 00 ↔ `DESIGN.md`. Razón: lo verificable sin LLM se verifica sin LLM; el juicio queda para lo que no se puede reducir a reglas.
- **Hook en dos niveles.** `PostToolUse`: ruff solo sobre el `.py` editado (rápido, feedback inmediato). `Stop`: `make lint` y `make test` completos, con anti-bucle vía `stop_hook_active`. Razón: pyright y la suite completa son demasiado lentos por edición, pero ningún turno termina sin pasar por ellos; si la falla persiste tras un reintento, se reporta en lugar de encerrar al agente.

Abiertas:
- **Falsos positivos del detector:** números largos (claves de rastreo, ids). Mitigación: exigir dígito verificador o Luhn. Riesgo residual: un número al azar que pase el checksum (~10 %); se acepta, porque es preferible fallar de más.
- **Límite del sensor:** cubre logs, stdout, stderr y excepciones de los tests, no las trazas persistidas. Cuando existan trazas en SQLite, la spec 05 debe revisar también lo persistido (`test_persisted_traces_have_no_sensitive_data`, pendiente en la invariante 4 de DESIGN.md).

## Cambios durante la implementación

<!-- Se llena al cerrar. -->

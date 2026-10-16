# Spec 01b — Harness de desarrollo

**Estado:** cerrada
**Depende de:** spec-01

## Objetivo

Que las reglas no negociables se verifiquen con sensores automáticos durante el desarrollo, no solo por escrito, antes de construir la frontera de seguridad (spec 02).

## Fuera de alcance

- CI y pre-commit de git, por tiempo (el presupuesto va a seguridad y evals). Sustituto: `make check` antes de cada commit, regla de `AGENTS.md`. Riesgo residual en DESIGN.md.
- Enmascarado real: `mask()` es de la spec 02; aquí solo se **detecta**.
- Reglas para el frontend (spec 07).

## Contratos

- **`make check`** = `make lint` → `make test` → `make check-docs`. Único punto de verificación que no depende de la herramienta del agente.
- **`make lint`** = ruff (check + format) + pyright + `lint-imports`. Pyright `standard`; los módulos críticos (enmascarado, gate, validador, executor) entran a la lista `strict` cuando existan.
- **Hooks de Claude Code** (`.claude/settings.json`):
  - `PostToolUse` (`Edit|Write`) → `ruff-on-edit.sh`: ruff solo sobre el `.py` editado; falla → código 2.
  - `Stop` → `verify-on-stop.sh`: `$VERIFY_ON_STOP_CMD` (por defecto `make lint && make test`); falla → código 2, salvo con `stop_hook_active: true` (anti-bucle: reporta y deja terminar).
- **Detector** `find_sensitive(text) -> list[Finding]` en `backend/domain/sensitive.py`: CLABE, tarjeta, `long_number`, RFC y CURP; la clave de rastreo SPEI no es sensible. Reglas y dirección de los errores en DESIGN.md, "Detección de datos sensibles".
- **Sensor de fugas en tests** (plugin `tests/sensitive_logs.py`, sin opción de desactivarlo): logs, stdout, stderr y excepciones de cada test. Puntos ciegos en DESIGN.md.
- **`/check-docs`**, híbrido y de solo lectura:
  - `scripts/check_docs.py` (`make check-docs`) verifica la tabla de invariantes de DESIGN.md y que las filas de `specs/README.md` coincidan con los archivos y estados de `specs/`;
  - después, el comando revisa la coherencia semántica entre la spec 00 y DESIGN.md.

## Contratos de arquitectura

`[tool.importlinter]` en `pyproject.toml`:

1. Capas: `backend.mock_core.api` → `backend.mock_core.repository` → `backend.domain`.
2. `backend.domain` no importa `fastapi`, `uvicorn` ni `backend.mock_core`.

## Criterios de aceptación

1. `make lint` pasa sobre el código actual, y pyright con la configuración del repo falla ante un error de tipos en un archivo temporal.
2. Con `pytester` (`runpytest_subprocess`), el sensor hace fallar un test que expone una CLABE, una tarjeta, un RFC o una CURP completos, y no falla con formas enmascaradas ni con 18 dígitos sin checksum válido.
3. `find_sensitive` detecta todos los identificadores de `data/customers.json`.
4. `lint-imports` pasa, y un import prohibido (`backend.domain` → `fastapi`) lo hace fallar.
5. Ambos hooks están registrados. `ruff-on-edit.sh` sale con 0 para archivos que no son `.py` y con 2 para un `.py` con error. `verify-on-stop.sh` sale con 2 si el comando falla y con 0 si `stop_hook_active` es `true`.
6. `make check-docs` pasa sobre el repo y falla, con fixtures temporales, ante un test inexistente, un enlace roto, una fila faltante o estados que no coinciden.
7. `make check` corre lint, test y check-docs en ese orden.

## Riesgos y decisiones

- **Pyright, no mypy:** velocidad en el hook y soporte de Pydantic v2 sin plugins.
- **`/check-docs` híbrido:** lo verificable sin LLM se verifica sin LLM; el juicio queda para lo que no se reduce a reglas.
- **Hooks en dos niveles:** pyright y la suite completa son lentos para correr en cada edición, pero ningún turno termina sin pasar por ellos; si la falla persiste tras un reintento, el hook la reporta en lugar de encerrar al agente.
- **Límites del detector y del sensor:** ver DESIGN.md. Las trazas persistidas quedan para la spec 05.

## Cambios durante la implementación

- `make check` se agregó antes del cierre, porque los hooks solo corren en Claude Code y AGENTS.md promete un setup independiente de la herramienta.
- `VERIFY_ON_STOP_CMD` permite probar el hook `Stop` sin recursión. El sensor vive como plugin para poder probarlo con `pytester`; `_run_inner` consume la salida que pytester re-emite.
- El sensor se extendió de logs a stdout, stderr y excepciones (`pytest_runtest_makereport`).
- El detector se endureció como base de `mask()`: separadores, `long_number` y la excepción de la clave de rastreo (17 de 82 claves del dataset daban falso positivo).
- `/check-docs` sumó reglas tras su primera corrida, que pasó en verde con 5 invariantes sin cobertura. Ahora son error: una fila sin tests ni pendientes, una fila solo parcial y un pendiente de una spec cerrada. Sus tests usan un repo sintético.
- DESIGN.md: coberturas parciales marcadas; la invariante 5 se parametrizó por vector, alineada con EVALS.md; se agregaron contratos de arquitectura pendientes para las invariantes 2 y 4.
- `pyright[nodejs]` trae su propio Node. pytest silencia solo la `StarletteDeprecationWarning` que emite `fastapi.testclient`.
- Bitácora en AI_NOTES (f08128c, 9e49c19, 6697845, segunda revisión de la spec 01b).

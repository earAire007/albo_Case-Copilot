# Spec 07 — Consola de operaciones

**Estado:** cerrada
**Depende de:** spec-06

## Objetivo

Que una persona de operaciones revise casos, entienda qué hizo el agente, ajuste la respuesta y apruebe o rechace la acción propuesta, sin ver datos sensibles completos.

## Fuera de alcance

- Autenticación/SSO: `approver` y `editor` son texto libre (riesgo residual).
- Diseño visual elaborado, tiempo real (alcanza con refrescar), envío real al cliente y edición de la acción propuesta.

## Contratos

**1. Edición persistente de la respuesta** (`backend/approval/`; pendiente de la 06):
- `PUT /cases/{id}/reply {editor, final_reply}` guarda en `cases.final_reply`, con `edited_by` y `edited_at`.
- **Sin enmascarado silencioso:** cualquier tramo de 13 a 19 dígitos que no sea una clave de rastreo **devuelta por las tools de ese caso** responde 422 con un mensaje claro.
  - La excepción es por procedencia, no por formato: `CC` + CLABE responde 422, igual que en la 05a.
  - La regla pasa a `backend/security/digits.py`, un módulo neutral que usan los validadores del agente y la edición (`backend.approval` no puede importar `backend.agent`).
- **Validaciones:** un `editor` vacío responde 422 y un caso inexistente, 404.
- **Ventana de edición:** solo mientras la propuesta no esté decidida, o en cualquier momento si el caso no tiene propuesta; si ya está decidida, 409.
- **Serialización:** la edición y la aprobación comparten el lock de la 06.
- **Traza:** cada edición queda como `reply_edited`, con el editor enmascarado.
- **Snapshot en la decisión:** `decisions` registra `reply_snapshot`, la respuesta vigente al decidir (`final_reply`, o `reply` si no hubo edición), enmascarada. La tabla sigue siendo solo de inserción.
- **Vista del caso:** `GET /cases/{id}` expone `reply` (la del modelo) y `final_reply`.
- **Traza de resultados de tools:** el loop de la 05b agrega la traza `tool_result` (herramienta y payload enmascarado). De ahí salen las claves eximibles, y la consola la muestra.

**2. Consola** (`console/`, React + Vite + TypeScript, sin librería de diseño; proxy de Vite a la API en `:8001`):
- **Bandeja:** casos con filtro por estado. Columnas: ticket, cliente, estado, tipo y fecha.
- **Detalle:** mensaje (enmascarado), `case_type`, `reasoning_summary`, respuesta del modelo, respuesta final editable con botón "Guardar", y la propuesta (acción, movimiento, justificación) con "Aprobar" y "Rechazar" (este con motivo) y un campo "operador". Muestra también la decisión y la ejecución, si existen.
- **Traza:** tools llamadas con sus argumentos y resultados, tokens, costo, latencia, rechazos con su validador, señales de injection por vector y paradas. **Nunca muestra thinking**; el razonamiento sale de la salida estructurada.
- **Errores de la API** (404, 409, 422): se muestran con su mensaje.

## Contratos de arquitectura

- Python: se mantienen los de la 06. La edición vive en `backend.approval`, que sigue sin importar `backend.agent`, y `backend/security/digits.py` es neutral.
- La consola solo habla con la API HTTP.

## Criterios de aceptación

1. `test_edit_reply_persists`: el `PUT` guarda y el `GET` muestra `final_reply` junto a `reply`. Un tramo de 16 dígitos sin checksum, o una CLABE, responde 422 con mensaje, sin enmascarar. Una clave de rastreo devuelta por las tools del caso se acepta.
2. `test_edit_reply_rejects_unproven_tracking_key`: `CC` + CLABE válida en la edición → 422.
3. `test_edit_reply_rules`: `editor` vacío → 422; caso inexistente → 404; propuesta ya decidida → 409.
4. `test_reply_edit_is_traced` y `test_decision_snapshots_current_reply`: la decisión guarda el texto vigente al aprobar (el editado, si lo hubo).
5. Consola: `make console-check` (`tsc --noEmit` + `vite build`) termina sin errores.
6. Consola: un test con Vitest sobre el detalle, con `fetch` simulado, verifica que muestra `reasoning_summary` y las tool calls, que no aparece thinking y que "Aprobar" llama al endpoint correcto.
7. Verificación manual documentada en README: webhook → worker → consola → aprobar.

## Riesgos y decisiones

Resueltas: React + Vite (spec 00); `make console-check` aparte, para que `make check` siga sin depender de Node; se edita hasta la decisión; en el cierre, la API sirve el build estático; excepción de la clave de rastreo por procedencia; la decisión guarda un snapshot de la respuesta.

- **Tiempo:** 60 min. Primer recorte: el test de Vitest (criterio 6), que pasa a verificación manual. El endpoint de edición no se recorta.
- **Cambio en la 05b, cerrada:** se agrega la traza `tool_result`. Es aditivo y queda enmascarado como el resto de las trazas.

## Cambios durante la implementación

- **Edición: RFC y CURP también responden 422** (no estaba en el contrato). Mismo principio que los dígitos: nada se enmascara en silencio. La detección corre sobre el texto normalizado (NFKC, sin invisibles, mayúsculas) con el detector de la 01b y con un patrón que admite separadores entre los segmentos fijos; lo guardado no se altera. Una primera versión pegaba los grupos quitando separadores, y el reviewer mostró que así un dígito vecino se pegaba al identificador y lo ocultaba (`Ref 1 GOCA…`), una regresión respecto del detector crudo.
- **Regla de dígitos endurecida en ambos lados** (hallazgo del security-reviewer, hueco presente desde la 05a). Antes de buscar: NFKC, sin caracteres `Cf` y sin horas bien formadas (`HH:MM[:SS]`). Separador: cualquier carácter que no sea letra ni dígito, `:` incluido, o una palabra de 1 a 3 letras con o sin espacios. La primera versión dejaba `:` fuera para no rechazar horas, y el reviewer mostró que así pasaba `646180:198384:020099`; se cambió a eximir solo horas válidas. Riesgo residual aceptado: palabras de 4+ letras entre grupos y dígitos disfrazados de una secuencia de horas (la última defensa es la aprobación humana). Falsos positivos aceptados en la dirección segura: listas de 3+ montos con comas.
- **`PRAGMA user_version`** (pedido en la revisión del plan): el `Store` falla con "esquema desactualizado: borra var/copilot.db" ante una base anterior. Sin migraciones.
- **`reply_snapshot` opcional**: una propuesta sin caso (solo en tests de la 06) registra `None`.
- **La vista del caso** expone además `edited_by`, `edited_at` y `proposal.execution`.
- **Cobertura de `tool_result` en datos persistidos**: `test_persisted_traces_have_no_sensitive_data` usa `run_turn` y no las genera; se agregó `test_persisted_rows_after_loop_have_no_sensitive_data`, que pasa por `run_case` con los 15 casos de eval.
- **Consola**: la traza se muestra por lista permitida; un paso desconocido aparece solo por nombre, sin su contenido, así que un bloque de thinking no se mostraría aunque llegara a persistirse. `make console-check` corre también Vitest. El criterio 6 no se recortó.
- **Estados tras la decisión** (ajuste de la 07, encontrado en la verificación manual: aprobar no cambiaba el estado y en la bandeja un caso decidido era indistinguible de uno pendiente; la 06 nunca definió ese estado). `approved`, `rejected` y `execution_failed`, asignados por el ledger en la misma transacción SQLite que los justifica: rechazar → `rejected`; aprobar → `execution_failed` (pesimista: si la ejecución lanza o el proceso muere antes, el caso nunca se ve aprobado, y queda la traza `execution_failed` con el tipo de error); la ejecución registrada → `approved`. Reintentar `approve` es idempotente y lleva a `approved`; la consola ofrece "Reintentar ejecución". Terminales para la decisión: las transiciones prohibidas siguen respondiendo 409, `set_case_status` rechaza esos estados y no sobrescribe un caso decidido (cierra la carrera del worker que guarda el estado después de `run_case`), y el worker no los reprocesa. `SCHEMA_VERSION` pasa a 2. Tests en `tests/test_case_status.py`.
- **Riesgo entre dos operadores** (editar mientras otro aprueba): documentado como residual en DESIGN.md; `expected_edited_at` queda en "qué haría con más tiempo", ligado a SSO.

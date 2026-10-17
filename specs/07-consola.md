# Spec 07 — Consola de operaciones

**Estado:** borrador
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

<!-- Se llena al cerrar. -->

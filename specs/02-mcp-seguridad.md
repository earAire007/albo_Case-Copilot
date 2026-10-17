# Spec 02 — Servidor MCP y frontera de seguridad

**Estado:** borrador
**Depende de:** spec-01, spec-01b

## Objetivo

Exponer el core simulado al agente como tools MCP de solo lectura, con el cliente fijado por capacidad, los datos sensibles enmascarados y el texto de terceros marcado como no confiable, todo verificado en código.

## Fuera de alcance

- Loop del agente, trazas y executor (spec 05). Enmascarar lo que escribe el modelo (spec 05).
- Transporte HTTP/SSE: solo stdio y sesión en memoria.
- Tool de resumen agregado.

## Contratos

- **Servidor** `mcp_server/server.py`: `create_server(repo: CoreRepository, customer_id: str) -> FastMCP` (SDK oficial). Cada sesión queda **fijada a un cliente al crearse**; el harness (spec 05) abre una por caso, por stdio (`python -m mcp_server --customer-id …`) o en proceso. Un `customer_id` inexistente falla al crear la sesión. Consume `CoreRepository` en proceso, sin HTTP contra la API mock.
- **Tools** (todas con `readOnlyHint=True` y ninguna con `customer_id` en su esquema):
  - `get_customer()`;
  - `list_transactions(type?, status?, from?, to?, cursor?, limit ≤ 20)` devuelve `{items, total, has_more, next_cursor}`, donde `total` cuenta los movimientos que cumplen el filtro; nunca el historial completo;
  - `get_spei_status(txn_id)` y `get_card_authorization(txn_id)`.

  Un `txn_id` de otro cliente o del tipo equivocado da el mismo error que uno inexistente.
- **`mask(obj)`** (`backend/security/masking.py`), aplicado a **toda** respuesta antes de salir del servidor:
  - CLABE y tarjeta → `****` + últimos 4; RFC, CURP y `long_number` → se borran por completo y quedan como etiqueta de tipo (`[RFC]`, `[CURP]`, `[LONG_NUMBER]`);
  - por campo (`clabe`, `card_number`, `rfc`, `curp`, `counterparty_clabe`) y, en cualquier otro string, por detector (`find_sensitive`, spec 01b), con las mismas reglas;
  - `tracking_key` nunca se enmascara: es campo exento y además el detector lo excluye.
- **`unmask(customer_id, field)`** (`backend/security/unmask.py`): devuelve el valor real desde el repositorio, nunca invirtiendo un texto enmascarado. Solo el executor puede importarlo, y no se expone como tool del MCP.
- **Texto de terceros:** `concept`, `counterparty_name` y `merchant` salen como `{"untrusted_text": "…", "source": "spei_ordenante" | "comercio"}`, para que la spec 05 los delimite.

## Contratos de arquitectura

1. `protected`: a `backend.security.unmask` solo lo importan los `allowed_importers`. Hoy la lista está vacía; la spec 05 agrega el executor.
2. `forbidden`: `mcp_server` no importa `backend.mock_core.api`, `fastapi` ni `backend.security.unmask`.
3. `masking.py` y `unmask.py` entran a la lista `strict` de pyright. `mcp_server` se agrega como paquete raíz de import-linter.

## Criterios de aceptación

1. `test_mcp_exposes_no_money_moving_tool`: el listado de tools es exactamente esas 4, todas con `readOnlyHint`, y ningún nombre coincide con `refund|reembols|transfer|pay|pago|send|withdraw|retiro`.
2. `test_mcp_tools_ignore_model_supplied_customer_id`: ningún esquema tiene `customer_id`; una llamada que agrega el `customer_id` de otro cliente se rechaza o se ignora y nunca devuelve datos ajenos; en el escenario `adv_other_account`, los `txn_id` del cliente objetivo dan "no encontrado".
3. `test_mask_applied_before_model_and_traces`: para los 20 clientes, ninguna respuesta serializada de ninguna tool tiene hallazgos de `find_sensitive`. El MCP es la única salida de datos hacia el modelo y las trazas; las trazas persistidas siguen pendientes de la spec 05.
4. `test_mask_reuses_detector_and_keeps_tracking_key`: la `tracking_key` sale intacta en `get_spei_status`; una CLABE dentro de texto libre sale como `****` + últimos 4, y un RFC, una CURP o un `long_number` salen como su etiqueta, sin dígitos residuales.
5. `test_untrusted_fields_are_marked`: los tres campos salen envueltos, y el `concept` del escenario `adv_tool_result_injection` llega intacto dentro de `untrusted_text`.
6. `test_list_transactions_is_capped`: `limit > 20` se rechaza, y la paginación recorre todo sin repetir ni omitir.
7. `test_list_transactions_reports_total_and_has_more`: con más de 20 movimientos, la primera página trae `total` igual al conteo real, `has_more = true` y cursor; en la última página, `has_more = false` y sin cursor.
8. `test_unmask_not_exposed_as_tool` y `lint-imports`: `unmask` no aparece entre las tools; los contratos 1 y 2 se cumplen, y un import de `unmask` desde `mcp_server` los rompe.

Al cerrar, en `DESIGN.md`: las invariantes 1 y 3 pasan de parcial a completas; en la invariante 4, los tests de esta spec dejan de estar pendientes, y el contrato de `unmask` queda `(pendiente, spec 05)`, solo para el executor.

## Riesgos y decisiones abiertas

Resueltas:

1. **Sesión por caso, fijada al cliente.** La garantía de scoping vive en el servidor y se prueba en esta spec; no depende de que el harness oculte un argumento.
2. **Enmascarado:** CLABE y tarjeta como `****` + últimos 4 (permite decir "terminación 5678"). RFC, CURP y `long_number` se borran por completo con su etiqueta de tipo: los últimos caracteres no sirven para identificarlos ante el cliente. La clave de rastreo nunca se enmascara.
3. **`unmask()` mínimo**, por consulta al repositorio, protegido por un contrato de import-linter y sin exponerse como tool. Ninguna acción actual lo necesita; el contrato vale por sí mismo.
4. **Campos no confiables:** `concept`, `counterparty_name` y `merchant`; los tres los escribe un tercero.
5. **Página de 20** (menos que el 50 de la API) con `total`, `has_more` y cursor, para que el modelo sepa que hay más movimientos sin recibirlos todos.

Riesgos:

- **A 10x casos, una sesión MCP por caso** (proceso o sesión en memoria) multiplica el arranque y la memoria. Mitigación posible: un pool de sesiones reutilizables que se vuelven a fijar por caso; no entra aquí.
- **Tiempo:** el máximo es 60 min. Si falta tiempo se recorta el arranque por stdio (basta la sesión en memoria); la seguridad no se recorta.
- **Proceso:** el subagente `security-reviewer` corre antes de cada commit de `mcp_server/` (lo exige `CLAUDE.md`).

## Cambios durante la implementación

<!-- Se llena al cerrar. -->

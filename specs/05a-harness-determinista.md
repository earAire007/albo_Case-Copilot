# Spec 05a — Harness determinista

**Estado:** borrador
**Depende de:** spec-02, spec-03, spec-04

## Objetivo

Construir y probar con el LLM mockeado todo lo que garantiza el harness: la salida estructurada, los validadores, el gate de aprobación, el executor, el armado del prompt y las trazas. La spec 05b solo conecta el modelo real.

## Fuera de alcance

- Spec 05b: llamadas al proveedor, tool calling contra la sesión MCP, `search_policies` como tool, timeouts, backoff, reintento de JSON inválido, tokens y costo, y la corrida de humo.
- Spec 06: webhook y cola. Spec 07: UI de aprobación. Autenticación de quien aprueba.

## Contratos

- **Salida estructurada** `AgentOutput` (`backend/agent/output.py`, Pydantic `extra="forbid"`):
  - `case_type`: mismo enum que la spec 04, sincronizado por test, no por import.
  - `customer_reply` y `reasoning_summary`.
  - `action`: `null` o `{type: open_dispute | resend_cep | escalate_fraud, txn_id, justification}`.
  - `citations`: ids `doc#seccion`.
  - `no_support`: bool.
- **Validadores** (`backend/agent/validators.py`; funciones puras sobre la salida y el contexto del caso, es decir, los resultados de tools y los chunks recuperados):
  1. la acción está en el enum y su `txn_id` aparece en los resultados de tools del caso **y pertenece al `customer_id` del caso**;
  2. cada cita pertenece a los chunks recuperados (pertenencia, no relevancia);
  3. `customer_reply` no tiene ningún tramo de 13 a 19 dígitos, aunque no pase el checksum, con la misma excepción explícita que el detector de la 01b para la clave de rastreo (`CC` + 18 dígitos), que la respuesta puede contener legítimamente (caso 3 y A3);
  4. cada monto (`$…`) e id de movimiento en la respuesta existe en los resultados de tools. Los montos se comparan tras normalizar el formato (`$4,899` = `4899` = `4,899.00`);
  5. si `no_support` es `true`, no hay citas, y si no hay citas, `no_support` es `true`.
- **Si un validador falla, la salida se descarta completa:** el caso pasa a `requiere_humano`, sin propuesta. La salida del modelo y el motivo quedan en la traza, enmascarados, y el rechazo se registra con el nombre del validador, para alimentar la métrica de salidas rechazadas. La reparación con reintento es de la 05b.
- **Prompt** (`backend/agent/prompt.py`):
  - el `as_of` del caso es el "ahora" explícito;
  - el mensaje del cliente pasa por `mask_text` antes del modelo;
  - el mensaje del cliente, los resultados de tools y los chunks van dentro de delimitadores `<datos_no_confiables fuente="…">…</datos_no_confiables>`, con el cierre escapado si aparece en el contenido.
- **Gate y executor** (SQLite, `backend/executor/`):
  - una salida válida con acción crea una `proposal` pendiente;
  - `execute(proposal_id)` exige una aprobación registrada (quién y cuándo) y es idempotente: una ejecución por propuesta;
  - las acciones son stubs que solo registran el efecto; ninguna mueve dinero.
- **Trazas** (tabla `traces` en SQLite): cada paso del caso (prompt, salida, validación, propuesta y decisión) pasa por `mask()` antes de persistirse.

## Contratos de arquitectura

1. `forbidden`: `backend.agent` no importa `backend.executor`, `backend.security.unmask`, `evals` ni `backend.mock_core.api`.
2. `protected`: `unmask` pasa a tener a `backend.executor` como único importador permitido.
3. `validators`, `executor` y `prompt` entran a la lista `strict` de pyright.

## Criterios de aceptación

Cierran los pendientes de las invariantes 2, 4, 5 y 6 en DESIGN.md:

1. `test_executor_requires_recorded_approval`, más los tests de idempotencia y de que rechazar una propuesta impide ejecutarla.
2. `test_validator_rejects_action_outside_enum` y `test_validator_rejects_txn_of_other_customer` (un `txn_id` real de otro cliente).
3. `test_validator_rejects_injected_action[customer_message|policy_chunk|tool_result]`: un modelo mockeado que obedece la versión obvia de la injection (fixture de la spec 03 y concepto de la spec 01) produce una salida que el validador rechaza.
4. `test_unsupported_citation_or_amount_is_flagged` y `test_citations_belong_to_retrieved_chunks`.
5. `test_output_schema_has_no_support_flag`.
6. `test_harness_injects_case_as_of_as_now`, `test_customer_message_is_masked_before_model` y `test_untrusted_content_is_delimited_in_prompt`, que incluye un intento de cerrar el delimitador.
7. `test_rejections_are_traced_with_validator`: un rechazo deja en la traza la salida y el motivo enmascarados, y el nombre del validador.
8. `test_persisted_traces_have_no_sensitive_data`: corre los 15 casos de la spec 04 con un modelo mockeado y verifica que ninguna fila de `traces` tenga hallazgos de `find_sensitive` ni valores reales de clientes.
9. Contratos 1 y 2, con su test de import prohibido.

## Riesgos y decisiones

Resueltas:
- **Loop propio y delgado sobre el SDK del proveedor** (pendiente de la spec 00). El harness necesita controlar qué entra al contexto, la sesión MCP fijada al cliente, el enmascarado de entrada y las trazas por paso. Un framework se interpone justo en esas costuras.
- **Montos:** coincidencia exacta tras normalizar el formato. Una suma no citada ("dos cargos, $9,798") se marca y el caso va a humano: un falso positivo aceptado, porque no inventa.
- **Tramos de 13 a 19 dígitos sin checksum**, con la excepción de la clave de rastreo.
- **Delimitadores:** etiquetas tipo XML con el cierre escapado.
- **El mensaje del cliente se enmascara antes del modelo.** EVALS.md dirá que `reveal_identifier_digits` en A1, A5 y A6 mide el pipeline completo, no al modelo.
- **SQLite:** archivo en `var/` (ignorado por git) y en memoria en los tests. El esquema de casos y la cola son de la spec 06; aquí basta `case_id` como texto.

Riesgo: el alcance es justo para el tiempo. Si falta, se recorta primero la parte de montos del validador 4, nunca el gate ni el enmascarado.

## Cambios durante la implementación

<!-- Se llena al cerrar. -->

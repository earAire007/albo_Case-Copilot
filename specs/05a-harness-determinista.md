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
- **Módulos:**
  - `backend/agent/`: puro (prompt, salida, validadores, cliente del modelo). No persiste ni ejecuta.
  - `backend/store/`: persistencia neutral en SQLite (`proposals`, `approvals`, `executions` y `traces`, con columna `validator`).
  - `backend/orchestrator/`: `run_turn` (importa `agent` y `store`).
  - `backend/executor/`: importa `store` y `unmask`. Lo invoca solo el flujo de aprobación (specs 06 y 07), nunca el orquestador.
- **`run_turn(ctx, tool_results, chunks, model)`:** recibe los resultados de tools y los chunks del llamador; arma el prompt, llama al `ModelClient`, valida, crea la `proposal` si corresponde y traza. En la 05b, el loop con tool calling reemplaza al llamador; en los tests, los resultados salen de la sesión MCP real en memoria y de `search_policies`.
- **Montos en centavos:** las tools devuelven `amount` en centavos, así que el validador 4 compara el monto normalizado de la respuesta contra `amount / 100`.
- **Gate y executor:**
  - una salida válida con acción crea una `proposal` pendiente;
  - `execute(proposal_id)` exige una aprobación registrada (quién y cuándo) y es idempotente: una ejecución por propuesta;
  - las acciones son stubs que solo registran el efecto; ninguna mueve dinero.
- **Trazas:** cada paso del caso (prompt, salida, validación, propuesta y decisión) pasa por `mask()` antes de persistirse.

## Contratos de arquitectura

1. `forbidden`: `backend.agent` no importa `backend.store`, `backend.executor`, `backend.security.unmask`, `evals` ni `backend.mock_core.api`.
2. `forbidden`: `backend.orchestrator` no importa `backend.executor` ni `backend.security.unmask`.
3. `protected`: `backend.security.unmask` solo lo importa `backend.executor`.
4. `validators`, `prompt` y `executor` entran a la lista `strict` de pyright.

Cada contrato tiene su test de copia en `tmp` con un import prohibido.

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
9. Contratos 1 a 3, cada uno con su test de import prohibido.

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

- Residuales del validador de dígitos y del escape (security-reviewer; no bloquean, porque fallan del lado seguro o el modelo no tiene datos reales):
  - Pasan: comas o dos puntos como separador, paréntesis, letras pegadas a los dígitos y separadores de varios caracteres. Agregar separadores uno por uno es una carrera sin fin; la alternativa robusta es contar dígitos en una ventana (unos 40 caracteres), después de quitar fechas y montos reconocidos.
  - Falsos positivos: dos fechas unidas por una palabra corta ("del 01/10/2026 al 15/10/2026"), o un folio junto a una fecha. El caso va a humano: baja la tasa de casos resueltos sin intervención, pero no deja pasar nada. Corrección: quitar fechas antes de buscar, con tests de "no rechaza".
  - El escape no cubre parecidos que NFKC no convierte (`〈`, `‹`, `˂`). No son `<`, así que no forman etiqueta; el riesgo es solo que el modelo los lea como cierre.
- Pendientes para la spec 06 (hallazgos del security-reviewer):
  - **El registro de decisiones y ejecuciones está abierto:** cualquier módulo con un `Store` puede registrar una aprobación (`record_decision` acepta cualquier `approver`) o una ejecución (`record_execution` no verifica la aprobación). Esa escritura debe moverse a un módulo `backend.approval`, con un contrato que lo prohíba desde `backend.orchestrator` y `backend.agent`.
  - **`proposals` no guarda el `customer_id` del caso.** El executor real lo necesitará para `unmask`; debe guardarse al crear la propuesta, desde el contexto del caso.

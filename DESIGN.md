# DESIGN

<!-- Documento vivo: cada spec agrega o actualiza su sección al cerrarse. -->

## Arquitectura del harness

Cuatro módulos con una frontera cada uno, vigilada por import-linter (spec 05a):

- **`backend/agent/`, puro:** arma el prompt (`as_of` como "ahora", mensaje del cliente enmascarado, todo contenido no confiable dentro de delimitadores que no puede cerrar), define la salida estructurada `AgentOutput` y la valida con funciones puras (`schema`, `action`, `citations`, `digits`, `facts`, `no_support`). No persiste ni ejecuta: no puede importar `store`, `executor`, `unmask`, `evals` ni la API mock.
- **`backend/store/`, neutral:** SQLite para el estado de la aplicación (propuestas, decisiones, ejecuciones y trazas). Todo texto libre se enmascara al insertarse.
- **`backend/orchestrator/`:** `run_turn` arma el prompt, llama al modelo, valida y deja una propuesta **pendiente** o manda el caso a humano, trazando cada paso y cada rechazo con su validador. No puede importar el executor ni `unmask`.
- **`backend/executor/`:** ejecuta solo propuestas con aprobación registrada, una vez, y solo acciones del enum; las acciones son stubs que no mueven dinero. Es el único módulo autorizado a importar `unmask`. Lo invoca el flujo de aprobación (specs 06 y 07), nunca el orquestador.

El loop con el modelo real y el tool calling contra la sesión MCP del caso son de la spec 05b, y reemplazan al llamador de `run_turn`.

Spec 06 agrega la entrada, la cola y el gate cerrado:

- **`backend/app/`:** el webhook idempotente (`Idempotency-Key`, mensaje enmascarado en reposo) y la API de casos, traza y aprobación para la consola.
- **`backend/worker/`:** cola en proceso sobre SQLite. Corre `run_case` con la sesión MCP del cliente del caso y no repite modelo ni propuesta en reintentos (`UNIQUE(case_id)`). No puede aprobar ni ejecutar.
- **`backend/store/ledger.py`:** el único que escribe decisiones y ejecuciones. Lo protege un contrato (solo `backend.executor` y `backend.approval`), verifica la aprobación en la misma transacción y sus tablas son solo de inserción.
- **`backend/approval/`:** aprobar (decisión más ejecución, idempotente) y rechazar, con estados terminales. No toca el modelo.
- **El `Store` serializa sus operaciones con un `RLock`,** porque la API y el worker comparten una conexión.

## Modelo de defensa

Invariantes definidas en `specs/00-fundamentos.md`. Cada una con los tests y contratos de arquitectura que la verifican. `(parcial: …)` indica qué parte cubre hoy; `(pendiente, spec NN)` indica qué spec la completa. `make check-docs` falla si una fila no tiene ni lo uno ni lo otro.

| # | Invariante | Tests y contratos |
|---|------------|-------------------|
| 1 | Sin capacidad de mover dinero | `test_mcp_exposes_no_money_moving_tool`; `test_mock_api_has_no_write_routes` |
| 2 | Planner/executor separados, gate humano en código | `test_executor_requires_recorded_approval`, `test_validator_rejects_action_outside_enum`, `test_validator_rejects_txn_of_other_customer_present_in_results`, `test_execution_requires_approval_in_same_transaction`, `test_ledger_tables_are_insert_only`, `test_concurrent_approve_and_reject_stay_consistent`; contrato `agent is pure: no store, executor, unmask, evals or API`; contrato `orchestrator never executes or unmasks`; contrato `ledger is protected: only the executor and the approval flow`; contrato `worker and orchestrator never approve or execute` |
| 3 | Scoping de `customer_id` por capacidad | `test_mcp_tools_ignore_model_supplied_customer_id`, `test_other_account_scenario_is_unreachable`; `test_endpoints_never_return_other_customer_data` |
| 4 | Enmascarado de datos sensibles en la frontera | `test_fixture_fails_on_raw_identifier`, `test_sensor_fails_on_print`, `test_sensor_fails_on_stderr`, `test_sensor_attributes_exception_message_leak` (parcial: logs, stdout, stderr y excepciones de tests); `test_mask_applied_before_model_and_traces`, `test_mask_reuses_detector_and_keeps_tracking_key`, `test_free_text_and_error_masking_through_mcp`, `test_non_mcp_errors_are_masked_over_stdio`; `test_persisted_traces_have_no_sensitive_data`, `test_store_masks_every_table`, `test_customer_message_is_masked_before_model`; contrato `unmask is protected` (solo `backend.executor`) |
| 5 | Contenido no confiable (clientes, políticas, resultados de tools) delimitado | `test_validator_rejects_injected_action[customer_message\|policy_chunk\|tool_result]`, `test_delimiter_variants_cannot_close_block`; `test_untrusted_content_is_delimited` (parcial: chunks de política y campos de terceros del MCP); `test_untrusted_content_is_delimited_in_prompt` |
| 6 | Groundedness verificada en código | `test_unsupported_citation_or_amount_is_flagged`, `test_output_schema_has_no_support_flag`, `test_harness_injects_case_as_of_as_now`, `test_citations_belong_to_retrieved_chunks` (verifica pertenencia, no relevancia: la relevancia la cubren `no_support` y el juez de groundedness de los evals) |

### Riesgo residual y cómo se detecta en producción

| Riesgo | Detección |
|--------|-----------|
| **Sensores de desarrollo sin enforcement fuera de Claude Code.** Los hooks (`.claude/settings.json`) solo corren en esa herramienta; con otro agente o en la terminal, la única barrera es la regla de `AGENTS.md` de correr `make check` antes de cada commit. Pre-commit y CI quedaron fuera por tiempo (spec 01b). | `make check` sobre `main` al revisar; con más tiempo, un job de CI con el mismo comando. |
| **El ledger se puede alterar con SQL crudo.** Las tablas `decisions` y `executions` son solo de inserción por triggers, pero desde `store.connection` se pueden borrar los triggers (`DROP TRIGGER`) y luego alterar el registro (spec 06). Requiere código malicioso o muy descuidado. | `test_decision_and_execution_writes_only_in_ledger` (guarda textual, incluye `DROP TRIGGER`); revisión de código. |
| **El webhook no autentica al emisor (sin firma HMAC; spec 06).** Cualquiera que alcance el endpoint puede crear casos. El impacto se limita a ruido y costo de modelo: un caso falso solo produce una propuesta que pasa por aprobación humana, y el `customer_id` debe existir. Además, el 422 por `customer_id` inexistente permite enumerar clientes (los ids son secuenciales), y `GET /cases` y `/cases/{id}/trace` no tienen autenticación (spec 00). | Volumen anómalo de casos por emisor o por cliente; costo por hora del modelo. |
| **El `approver` no se verifica (sin SSO; spec 06).** El cuerpo dice quién aprueba; solo se rechaza vacío. | Revisión de las decisiones registradas (quién, cuándo); con más tiempo, SSO. |
| **El contrato de `unmask` se puede evadir.** import-linter solo ve imports estáticos: `importlib.import_module(...)` lo evade, y `tests/`, `scripts/` y `data/` no son paquetes raíz de import-linter (spec 02). | Revisión de código. Complemento: `test_unmask_token_only_in_allowed_modules` falla si el token `unmask` aparece fuera de su módulo en `backend/`, `mcp_server/`, `scripts/` o `data/` (no detecta un nombre construido por concatenación). |

### Detección de datos sensibles

`find_sensitive(text)` (`backend/domain/sensitive.py`) devuelve tipo y posición, nunca el valor: reportar una fuga no la repite. Es la base de `mask()` (spec 02) y del sensor de fugas en tests (spec 01b). Ante la duda, sobre-detecta.

| Categoría | Regla |
|-----------|-------|
| CLABE | 18 dígitos con dígito de control válido |
| Tarjeta | 13–19 dígitos que pasan Luhn (incluye 18 dígitos que pasan Luhn pero no el dígito de CLABE) |
| Separadores | Grupos separados por un solo espacio o guion (≥3 dígitos salvo el último: cubre 4-4-4-4 y 3-3-11-1) se unen y se validan solo si el total mide 13–19 |
| `long_number` | Cualquier tramo contiguo de 20+ dígitos. Sin ventanas deslizantes: en tramos largos alguna ventana pasaría un checksum por azar |
| RFC / CURP | Solo patrón, sin dígito verificador |
| Clave de rastreo SPEI | `CC` + 18 dígitos: **no** es sensible (se necesita para consultar el SPEI y reenviar el CEP). Excepción por formato exacto, no por "letras pegadas", que dejaría pasar una CLABE escrita junto a texto |

Dirección de los errores:

- **Falsos positivos aceptados:** un número de 13–19 dígitos que pase un checksum por azar (~10 %), cualquier número de 20+ dígitos, formatos tipo RFC/CURP. Sin la excepción, 17 de las 82 claves de rastreo del dataset se detectaban como CLABE o tarjeta.
- **Falsos negativos conocidos:** una CLABE o tarjeta escrita como `CC` + 18 dígitos; grupos separados cuyo total no mide 13–19 aunque una parte sí (una tarjeta seguida de más grupos); separadores distintos de un solo espacio o guion.

Sensor de fugas en tests (`tests/sensitive_logs.py`, sin opción de desactivarlo): revisa logs (handler en el root logger a DEBUG), stdout, stderr y el texto de excepciones de cada fase (`pytest_runtest_makereport`, sin pedir `capsys`/`capfd`). Puntos ciegos: salida que el test consume con `capsys.readouterr()`, corridas con `-s`, excepciones atrapadas que nunca se imprimen ni se loguean, y trazas persistidas (pendiente, spec 05a).

## Contexto y costos

<!-- spec 02 y 05 -->

## Manejo de fallas del proveedor

Spec 05b, `backend/orchestrator/loop.py`. Los reintentos son del harness (`max_retries=0` en el SDK), para trazar cada uno:

| Falla | Tratamiento |
|---|---|
| Timeout, 429, 5xx, error de conexión | Backoff exponencial con jitter, hasta 3 reintentos; agotados, el caso va a humano |
| 4xx no transitorio (`ModelRequestError`) | El caso va a humano de inmediato; se traza el tipo de error, nunca el mensaje del SDK |
| `refusal`, `max_tokens` | El caso va a humano, sin fallbacks del servidor |
| Salida con formato inválido (`schema`, `no_support`) | Un reintento de reparación con los valores permitidos, nunca con el texto rechazado |
| Rechazo de seguridad o de sustento (`action`, `digits`, `citations`, `facts`) | El caso va a humano, sin reintento |
| Presupuesto excedido (6 tools o 30 000 tokens por caso) | El caso va a humano |
| Una tool lanza una excepción o devuelve algo que no es JSON | Error de tool genérico para el modelo; se traza `tool_error` |

La salida estructurada (`output_config.format`) hace raras las reparaciones: en la segunda corrida de humo hubo 0 rechazos de formato.

## Observabilidad y alertas

<!-- spec 05a (trazas) y 05b (tokens, costo y latencia por paso; detector de injection) -->

- **Por paso del modelo** (traza `model_step`): tokens de entrada y salida, costo con precios verificados, latencia, reintentos y motivo de término. Se persisten también las señales de injection, los rechazos con su validador, las paradas con su motivo, `provider_error` y `tool_error`.

- **Detector de injection (spec 05b):** heurística barata sobre el mensaje del cliente, los resultados de tools y los chunks, registrada en la traza por vector. No es garantía (invariante 5): alimenta la columna "detectado" de EVALS.md junto a "bloqueado".

## Trade-offs y decisiones

- **Minimización de datos en reposo (spec 06):** del mensaje del cliente solo se guarda la versión enmascarada. El original no se conserva: ninguna acción lo necesita, y el prompt ya lo enmascaraba.
- **Sin fallbacks del servidor ante rechazos del modelo** (spec 05b). En este sistema, un rechazo es más probable ante contenido adversarial, y reintentar con otro modelo sería buscar uno que acepte la injection. El rechazo va a `requiere_humano` y queda como señal en la traza. Los fallbacks pueden ser una variante en la comparación del cierre.
- **Loop propio y delgado sobre el SDK del proveedor, no un framework de agentes** (spec 05a; resuelve el pendiente de la spec 00). El harness necesita controlar qué entra al contexto, la sesión MCP fijada al cliente, el enmascarado de entrada y las trazas por paso; un framework se interpone justo en esas costuras.

## Qué recorté y por qué

<!-- -->

## Qué se rompe a 10x casos o con diez agentes compartiendo herramientas

- **La serialización de la aprobación (spec 06).** El `RLock` del `Store` serializa dentro de un solo proceso. Con varias réplicas de la API, o el worker en otro proceso, la carrera de aprobación vuelve: se repetiría la prueba de 300 rondas con respuestas incoherentes. La serialización debe bajar a la base de datos, con bloqueo de fila o una transacción serializable en un motor como Postgres. SQLite y la cola en proceso tampoco escalan a varios workers.

## Qué haría con más tiempo

- **Mitigar la enumeración de clientes en el webhook** (spec 06): responder igual para `customer_id` existentes e inexistentes (202) y fallar de forma asíncrona en el worker (caso a `requires_human`), en lugar del 422 actual.
- **Un caso de control sin injection por vector** (spec 04): A3 confunde la injection en el concepto con una política de CEP escrita desde quien paga. Con un control idéntico pero sin injection, una falla se atribuiría a la injection o a la interpretación de la política.

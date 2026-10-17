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
| 4 | Enmascarado de datos sensibles en la frontera | `test_fixture_fails_on_raw_identifier`, `test_sensor_fails_on_print`, `test_sensor_fails_on_stderr`, `test_sensor_attributes_exception_message_leak` (parcial: logs, stdout, stderr y excepciones de tests); `test_mask_applied_before_model_and_traces`, `test_mask_reuses_detector_and_keeps_tracking_key`, `test_free_text_and_error_masking_through_mcp`, `test_non_mcp_errors_are_masked_over_stdio`; `test_persisted_traces_have_no_sensitive_data`, `test_persisted_rows_after_loop_have_no_sensitive_data`, `test_loop_traces_tool_results_masked`, `test_store_masks_every_table`, `test_edit_reply_persists`, `test_edit_reply_rejects_rfc_and_curp_in_any_spelling`, `test_customer_message_is_masked_before_model`, `test_untrusted_block_masks_direct_input`, `test_unmask_token_only_in_allowed_modules`; contrato `unmask is protected` (solo `backend.executor`) (parcial: `mask()` no normaliza; un identificador escrito de otra forma, p. ej. un RFC en minúsculas o una CLABE separada por comas, en el mensaje del cliente o en un resultado de tool llega al modelo y a las trazas sin enmascarar; ver riesgo residual "El detector de la 01b no normaliza") |
| 5 | Contenido no confiable (clientes, políticas, resultados de tools) delimitado | `test_validator_rejects_injected_action[customer_message\|policy_chunk\|tool_result]`, `test_delimiter_variants_cannot_close_block`; `test_untrusted_content_is_delimited` (parcial: chunks de política y campos de terceros del MCP); `test_untrusted_content_is_delimited_in_prompt`; `test_tool_results_are_delimited_in_conversation`, `test_policy_results_are_delimited_in_conversation`, `test_untrusted_block_masks_direct_input` (camino de producción, `run_case`) |
| 6 | Groundedness verificada en código | `test_unsupported_citation_or_amount_is_flagged`, `test_output_schema_has_no_support_flag`, `test_no_support_is_coherent_with_citations`, `test_harness_injects_case_as_of_as_now`, `test_citations_belong_to_retrieved_chunks` (verifica pertenencia, no relevancia: la relevancia la cubren `no_support` y el juez de groundedness de los evals) |

### Riesgo residual y cómo se detecta en producción

Las señales salen de lo que el sistema ya persiste: `model_step` (costo y latencia por paso), `injection_signal` (por vector), `rejection` (por validador; `Store.rejection_counts()`), `stop`, `worker_error` y `provider_error`, el `status_reason` de cada caso y las tablas `decisions` y `executions`. Hoy no hay endpoint ni tablero que las agregue: son consultas sobre el `Store`. Las ediciones rechazadas con 422 **no se trazan** (`edit_reply` falla antes de escribir); solo quedan en el access log de uvicorn como `PUT /cases/{id}/reply 422`.

| Riesgo | Cómo se detecta en producción |
|--------|-------------------------------|
| **Sensores de desarrollo sin enforcement fuera de Claude Code.** Los hooks (`.claude/settings.json`) solo corren en esa herramienta; con otro agente o en la terminal, la única barrera es la regla de `AGENTS.md` de correr `make check` antes de cada commit. Pre-commit y CI quedaron fuera por tiempo (spec 01b). | Riesgo de desarrollo, sin señal en producción: `make check` sobre `main` al revisar; con más tiempo, un job de CI con el mismo comando. |
| **El ledger se puede alterar con SQL crudo.** Las tablas `decisions` y `executions` son solo de inserción por triggers, pero desde `store.connection` se pueden borrar los triggers (`DROP TRIGGER`) y luego alterar el registro (spec 06). Requiere código malicioso o muy descuidado. Lo mismo vale para `cases.status` (spec 07): los estados decididos los asigna solo el ledger y `set_case_status` los rechaza, pero un `UPDATE` crudo podría marcar un caso `approved` sin ejecución. No habilita ninguna ejecución (el gate lee `decisions`), solo mentiría en la bandeja; un trigger sobre `cases.status` lo cerraría. | Conciliación periódica: casos `approved` sin fila en `executions`, ejecuciones sin decisión `approved`, y aprobaciones por aprobador contra la traza del caso. En desarrollo, `test_decision_and_execution_writes_only_in_ledger` (guarda textual, incluye `DROP TRIGGER`) y revisión de código. |
| **El webhook no autentica al emisor (sin firma HMAC; spec 06).** Cualquiera que alcance el endpoint puede crear casos. El impacto se limita a ruido y costo de modelo: un caso falso solo produce una propuesta que pasa por aprobación humana, y el `customer_id` debe existir. Además, el 422 por `customer_id` inexistente permite enumerar clientes (los ids son secuenciales), y `GET /cases` y `/cases/{id}/trace` no tienen autenticación (spec 00). | Casos por hora y por `customer_id`; costo por hora (suma de `cost_usd` de `model_step`); picos de `injection_signal` por vector (una campaña de injection llega por aquí); 422 de `customer_id` inexistente en el access log (enumeración). |
| **El `approver` no se verifica (sin SSO; spec 06).** El cuerpo dice quién aprueba; solo se rechaza vacío. | Aprobaciones por aprobador (`decisions.approver`, `decided_at`): un nombre nuevo, un volumen atípico o aprobaciones en segundos tras la propuesta. Con más tiempo, SSO. |
| **Degradación o mala configuración del proveedor (specs 05b y 07).** Sin credenciales, con 429/5xx sostenidos o con latencia alta, los casos van a humano: nada se ejecuta, pero operaciones absorbe la carga. | Tasa de `requires_human` por motivo (`status_reason`: configuración, proveedor no disponible, presupuesto); latencia p95 y costo por caso desde `model_step`; el aviso de arranque sin credenciales en el log. |
| **Ofuscaciones que la regla de dígitos no persigue (specs 05a y 07).** La regla rechaza 13+ dígitos unidos por cualquier separador que no sea letra ni dígito, o por palabras de 1 a 3 letras, después de NFKC y de quitar caracteres invisibles y horas bien formadas. Pasan los dígitos partidos por palabras de 4+ letras ("646180 luego 522488216773") o disfrazados de una secuencia de horas ("6:46 18:01 9 …"); en la edición, un RFC o CURP con letras separadas una por una, el prefijo partido u homoglifos que NFKC no convierte. Las reglas deterministas no pueden cubrir todas las ofuscaciones: la última defensa es la persona que aprueba, y eso es parte del diseño. Falsos positivos aceptados en la dirección segura: una lista de 3+ montos separados por comas se rechaza como tramo de dígitos (el caso va a humano), y en la edición "pago 260718 por" puede leerse como RFC (422 con mensaje; la persona reescribe). | Una ofuscación que pasa no deja señal propia: la detección es muestreo de `reply_snapshot` aprobados. Alrededor: rechazos por validador (`digits`), 422 de edición en el access log (un operador que reintenta varias veces) y el diagnóstico del runner (spec 08), que guarda la salida rechazada y su motivo. |
| **El detector de la 01b no normaliza (spec 07).** La regla de dígitos (salida del modelo y edición) y la detección de RFC/CURP en la edición normalizan NFKC, invisibles, mayúsculas y separadores ampliados; `mask()` no. Un RFC en minúsculas o una CLABE separada por comas en el mensaje del cliente o en un resultado de tool llega al modelo y a las trazas sin enmascarar. | Ninguna automática hoy. Un barrido periódico de las trazas con la normalización de `digits.py` lo encontraría sin cambiar `mask()`; la corrección es la spec de normalización (ver "Qué haría con más tiempo"). |
| **Costo operativo medido de fallar cerrado (spec 08).** En la corrida comparativa, los validadores mandaron a humano 2 de 30 salidas legítimas, ambas con la propuesta correcta: una por la regla de dígitos de la 05a ("4,899.00 el 2026-10-12 con 1.5": monto y fecha unidos por palabras cortas) y otra por la regla endurecida de la 07 (montos separados por comas) junto con `facts` (un total derivado, $27,596.00, que no aparece literal en las tools). El endurecimiento de la 07 no cambió el destino de ningún caso en esta muestra. Ningún dato llegó al cliente: el costo es trabajo de operaciones, no seguridad. | Tasa de `requires_human` con motivo "no pasó las validaciones" y rechazos por validador; cuántos de esos casos aprueba después una persona sin cambiar la acción (falso positivo probable). Offline, el diagnóstico del runner (`make evals CASES=…`). |
| **Respuesta sin sustento dentro del alcance permitido (spec 08).** `facts` verifica datos (montos, ids) contra las tools, no afirmaciones. En la ronda 2, el agente dijo "cuando se liquide podrás obtener el CEP" (caso 07, Sonnet), y la política dice que un movimiento liquidado puede no tenerlo: no lo vieron ni el etiquetador humano ni `facts`, solo el juez. Mitigación: cada respuesta pasa por aprobación humana antes de enviarse. | Tasa de respuestas que operaciones edita antes de aprobar (`final_reply` distinta de `reply`), por tipo de caso; y el juez de groundedness sobre un muestreo periódico de respuestas aprobadas, cuando reciba la evidencia completa (ver "Qué haría con más tiempo"). |
| **Edición y aprobación entre dos operadores (spec 07).** No hay carrera de datos (el lock serializa), pero si B edita la respuesta mientras A la tiene abierta y A aprueba, la decisión registra un texto que A no vio. | Decisiones cuyo aprobador no es el autor del último `reply_edited` y con esa edición pocos minutos antes: `reply_snapshot` dice qué texto se aprobó, y la traza quién lo editó y cuándo. |
| **El contrato de `unmask` se puede evadir.** import-linter solo ve imports estáticos: `importlib.import_module(...)` lo evade, y `tests/`, `scripts/` y `data/` no son paquetes raíz de import-linter (spec 02). | Sin señal en producción: revisión de código. Complemento: `test_unmask_token_only_in_allowed_modules` falla si el token `unmask` aparece fuera de su módulo en `backend/`, `mcp_server/`, `scripts/` o `data/` (no detecta un nombre construido por concatenación). |

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

Sensor de fugas en tests (`tests/sensitive_logs.py`, sin opción de desactivarlo): revisa logs (handler en el root logger a DEBUG), stdout, stderr y el texto de excepciones de cada fase (`pytest_runtest_makereport`, sin pedir `capsys`/`capfd`). Puntos ciegos: salida que el test consume con `capsys.readouterr()`, corridas con `-s`, excepciones atrapadas que nunca se imprimen ni se loguean. Las trazas persistidas no son un punto ciego: las cubre `test_persisted_traces_have_no_sensitive_data` (spec 05a).

## Contexto y costos

<!-- spec 02 y 05 -->

## Manejo de fallas del proveedor

Spec 05b, `backend/orchestrator/loop.py`. Los reintentos son del harness (`max_retries=0` en el SDK), para trazar cada uno:

| Falla | Tratamiento |
|---|---|
| Timeout, 429, 5xx, error de conexión | Backoff exponencial con jitter, hasta 3 reintentos; agotados, el caso va a humano |
| Sin credenciales, 401 o 403 (`config_error`) | El caso va a humano en el primer intento, sin llamar al proveedor si no hay credencial; al arrancar sin credenciales la app lo avisa en el log |
| Otro 4xx no transitorio (`ModelRequestError`) | El caso va a humano de inmediato; se traza el tipo de error, nunca el mensaje del SDK |
| Excepción inesperada en el worker (`worker_error`) | Un reintento del job; agotado, el caso va a humano |
| `refusal`, `max_tokens` | El caso va a humano, sin fallbacks del servidor |
| Salida con formato inválido (`schema`, `no_support`) | Un reintento de reparación con los valores permitidos, nunca con el texto rechazado |
| Rechazo de seguridad o de sustento (`action`, `digits`, `citations`, `facts`) | El caso va a humano, sin reintento |
| Presupuesto excedido (6 tools o 30 000 tokens por caso) | El caso va a humano |
| Una tool lanza una excepción o devuelve algo que no es JSON | Error de tool genérico para el modelo; se traza `tool_error` |

Un caso en `requires_human` o `execution_failed` lleva `status_reason`: un motivo del catálogo de la spec 07 (`backend/app/status_reason.py`), elegido por la traza y sin copiar su texto, que la consola muestra junto al estado.

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

El presupuesto fue primero a seguridad y evals; lo recortado tiene un sustituto o queda como riesgo residual.

- **CI y pre-commit** (spec 01b): `make check` antes de cada commit, regla de `AGENTS.md`. Riesgo residual arriba.
- **Autenticación** (specs 00, 06 y 07): sin firma HMAC en el webhook ni SSO para operadores; `approver` y `editor` son texto libre. El puerto de Docker solo escucha en `127.0.0.1`.
- **Modo sin modelo para la demo** (spec 08): sin key, el caso va a `requires_human` con su motivo y la consola funciona igual. Un mock del modelo en producción habría sido otro camino que probar.
- **Repeticiones y significancia** (spec 08): una corrida por caso y variante, por presupuesto. Con 15 casos, p95 ≈ máximo, y así se reporta.
- **Más casos y un control por vector** (specs 04 y 08): ver "Qué haría con más tiempo".
- **Embeddings y reranking** (spec 03): BM25 propio, determinista y sin dependencias, alcanza para 15 casos y deja el recall medible.
- **Transporte HTTP del MCP** (spec 02): solo stdio y sesión en memoria; el worker levanta el servidor en proceso.
- **Consola en tiempo real y diseño visual** (spec 07): alcanza con refrescar.
- **Modelo del juez configurable** (spec 08): `JUDGE_MODEL` salió de `.env.example`; el juez validado contra las etiquetas humanas es `claude-opus-5-5` fijo.

Recortes previstos que al final no se aplicaron: la edición de la respuesta pasó de la 06 a la 07 y se hizo; el test de Vitest de la 07 se mantuvo; el juez de la 08 se recortó y después se recuperó y validó con dos rondas de etiquetas humanas.

## Qué se rompe a 10x casos o con diez agentes compartiendo herramientas

- **La serialización de la aprobación (spec 06).** El `RLock` del `Store` serializa dentro de un solo proceso. Con varias réplicas de la API, o el worker en otro proceso, la carrera de aprobación vuelve: se repetiría la prueba de 300 rondas con respuestas incoherentes. La serialización debe bajar a la base de datos, con bloqueo de fila o una transacción serializable en un motor como Postgres.
- **SQLite con una conexión compartida.** API, worker y trazas pasan por la misma conexión y el mismo lock: cada caso escribe decenas de filas de traza, y a 10x esas escrituras compiten con las aprobaciones de la consola. SQLite admite un solo escritor; con varios procesos hace falta un motor con concurrencia real.
- **Cola en proceso con un solo worker.** `run_once` procesa un job a la vez y la espera crece en línea con el volumen; el límite real es el rate limit del proveedor, que con 10x llegaría como 429 y, agotados los reintentos, como `requires_human` por proveedor no disponible. Varios workers necesitan una cola externa y control de concurrencia contra el proveedor.
- **Una sesión MCP por caso.** Cada caso crea su servidor MCP en proceso, fijado al `customer_id` del caso: es la frontera de scoping y no se debe compartir entre clientes. A 10x el costo es el arranque por caso; con diez agentes compartiendo herramientas, lo que escala es un servicio MCP aparte donde el harness fije el cliente por sesión autenticada, nunca un `customer_id` que elija el modelo.
- **N+1 de trazas en `GET /cases`.** Por cada caso, `_case_view` lee sus trazas cuatro veces (respuesta, razonamiento, respuesta del modelo y `status_reason`), la tabla `traces` no tiene índice por `case_id` y la bandeja no pagina. A 10x casos son 4·N barridos de una tabla que también crece 10x. La corrección: índice por `case_id`, una sola lectura por caso y paginación.

## Qué haría con más tiempo

- **Mitigar la enumeración de clientes en el webhook** (spec 06): responder igual para `customer_id` existentes e inexistentes (202) y fallar de forma asíncrona en el worker (caso a `requires_human`), en lugar del 422 actual.
- **Un caso de control sin injection por vector** (spec 04): A3 confunde la injection en el concepto con una política de CEP escrita desde quien paga. Con un control idéntico pero sin injection, una falla se atribuiría a la injection o a la interpretación de la política.
- **Aprobación condicionada a la versión vista** (spec 07): que `approve` reciba `expected_edited_at` (o un hash de la respuesta) y responda 409 si cambió desde que el operador la abrió. Tiene sentido junto con SSO, cuando `approver` y `editor` sean identidades verificadas.
- **Normalizar también en el detector de la 01b** (spec 07): la regla de dígitos y la edición ya normalizan (NFKC, invisibles, mayúsculas, separadores), pero `mask()` no. Un RFC en minúsculas o una CLABE con comas en el mensaje del cliente llega al modelo y a las trazas sin enmascarar. Requiere su propia spec, porque cambia la frontera de la invariante 4 y su tasa de falsos positivos.
- **Sonnet 5.5 con su esfuerzo por defecto (`high`)** (spec 08): la comparación del cierre fija `EFFORT=medium` en ambas variantes para aislar el modelo. Falta medir si Sonnet en `high` cierra la brecha de exactitud con Opus a menor costo.
- **Validar montos y fechas como entidades antes de buscar tramos de dígitos** (spec 08): reconocer y retirar montos (`$4,899.00`), fechas y horas antes de aplicar la regla de dígitos, en vez de ampliar separadores. Es la corrección que la 05a dejó propuesta (quitar fechas) y que habría evitado los dos rechazos por `digits` medidos en la corrida comparativa.
- **Aceptar montos derivados verificados en código** (spec 08): que `facts` acepte una suma o diferencia si el código la recalcula a partir de montos de las tools, en lugar de rechazar todo monto que no aparezca literal.
- **Paquete de evidencia completo para el juez y una ronda 3** (spec 08): darle `as_of` y la propuesta estructurada, y definir en la rúbrica el criterio para respuestas correctas con `no_support`. Cuatro de los cinco desacuerdos de R2 vinieron de ahí. La ronda 3 se corre con etiquetas nuevas, sin ajustar ni repetir R2.
- **Modelo del juez configurable** (spec 08): hoy es `claude-opus-5-5` fijo, el único validado contra las etiquetas humanas; otro modelo exige repetir esa validación antes de presentar sus resultados.
- **Trazar las ediciones rechazadas** (spec 07): un 422 de `PUT /cases/{id}/reply` deja hoy solo una línea en el access log. Una traza con la regla que falló (dígitos o RFC/CURP), sin el texto, daría la tasa de rechazos humanos junto a la del modelo.
- **Métricas agregadas consultables** (specs 05b a 08): un endpoint con rechazos por validador, `requires_human` por motivo, aprobaciones por aprobador, costo y latencia p95, que hoy son consultas sobre el `Store`.
- **Bandeja con índice y paginación** (spec 07): índice por `case_id` en `traces`, una sola lectura por caso y paginación en `GET /cases` (ver "Qué se rompe a 10x").

## Tiempo invertido

Del primer commit (2026-10-16 12:14) al último (2026-10-17 15:34) pasaron ~27 h. Contando solo los tramos entre commits y cortando en pausas de más de 45 min, el tiempo activo es **~13 h 40 min** en 6 sesiones (~11 h 40 min si el corte es a 30 min). Es un mínimo: no cuenta lo previo al primer commit de cada sesión ni la lectura sin commit.

El excedente sobre las 6 a 8 h sugeridas se fue en tres lugares: la spec 01b (sensores de desarrollo, ~1 h 45 min contra 45 estimados), la verificación manual desde un clon limpio con sus dos bugs, y las dos rondas del juez con etiquetado humano.

| Spec | Estimado | Real (según commits) |
|------|----------|----------------------|
| 00 | 20 min | n/d: sus commits están intercalados con la 01 y la 01b |
| 01 | 45 min | ~40 min (14:05–14:44) |
| 01b | 45 min | ~1 h 45 min (16:04–17:47) |
| 02 | 60 min | ~55 min |
| 03 | 40 min | ~17 min |
| 04 | 30 min | ~30 min |
| 05a | 70 min | ~16 min de implementación |
| 05b | 50 min | ~42 min |
| 06 | 70 min | ~33 min |
| 07 | 60 min | ~65 min |
| 08 | 1 h 30 min | ~6 h transcurridas, ~4 h 40 min sin la pausa de 10:41–12:03 |
| Cierre | 30 min | pendiente |

Las specs de código puro salieron en tiempo o antes, con el agente implementando contra tests escritos primero. Las que se pasaron, 01b y 08, crecieron al verificarse: la 01b ajustó su spec antes del código (hook Stop inyectable, cobertura por invariante) y sumó `make check` y el sensor de stdout, stderr y excepciones; la 08 sumó etiquetado manual, dos rondas del juez y los dos bugs del clon limpio.

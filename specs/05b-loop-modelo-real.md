# Spec 05b — Loop con el modelo real

**Estado:** cerrada
**Depende de:** spec-05a

## Objetivo

Conectar el harness determinista de la 05a con el modelo real: el loop de tool calling contra la sesión MCP del caso, el manejo de fallas del proveedor, los costos por paso y el detector heurístico de injection. Todo con tests deterministas sobre un proveedor falso, más una corrida de humo opcional con la key real.

## Fuera de alcance

- Runner de evals, LLM-as-judge y comparación de variantes (cierre).
- Webhook y cola (spec 06), consola (spec 07), streaming.
- Cambiar los validadores, el gate o el executor de la 05a.

## Contratos

- **Puerto del modelo** (`backend/agent/model.py`, puro): `ToolCallingModel.step(system, messages, tools) -> ModelStep(blocks, stop_reason, usage)`, con dataclasses propias. El adaptador `backend/llm/` traduce desde y hacia el SDK oficial de Anthropic.
- **Adaptador:**
  - modelo por defecto `claude-opus-5-5` (tabla de modelos de la referencia oficial de la API, 2026-10-06); precios de $4 / $20 por millón de tokens de entrada / salida, verificados el 2026-10-16 contra la página oficial de precios (https://platform.claude.com/docs/en/about-claude/pricing, fila "Claude Opus 5.5"); modelo, esfuerzo (`EFFORT`, inicial `medium`, el valor por defecto de ese modelo), precios y timeout se configuran por entorno;
  - `tool_choice` en `auto`, porque el modelo no acepta uno forzado;
  - el cliente se crea con `max_retries=0`: los reintentos son nuestros, para trazarlos e inyectar el sleep en los tests;
  - **sin fallbacks del servidor:** un `refusal` va a `requiere_humano`, con el motivo en la traza como señal.
- **Thinking:** el modelo siempre piensa. El loop devuelve la respuesta completa del asistente en cada turno, con los bloques de thinking sin cambios, pero las trazas **no** persisten esos bloques: solo el texto, las llamadas a tools y `reasoning_summary`.
- **Motivos de término:** `refusal` y `max_tokens` van a `requiere_humano`, con el motivo trazado.
- **Loop** `run_case(store, ctx, session, model)` en `backend/orchestrator/`:
  - Las tools que ve el modelo son las de `list_tools` de la sesión MCP fijada al cliente del caso, más `search_policies(query, k)` como tool del harness (sin `index` en su esquema).
  - Cada resultado de tool entra a la conversación enmascarado y dentro de `<datos_no_confiables>`, igual que en el prompt de la 05a.
  - Un `k` inválido u otro error de tool vuelve al modelo como error de tool; el caso no se interrumpe.
  - La salida final pasa por la misma validación de la 05a y termina en propuesta pendiente, respuesta o `requiere_humano`.
- **Presupuesto por caso:** valor inicial conservador de **6 llamadas a tools** y **30 000 tokens** (entrada más salida). Si se excede, el caso pasa a `requiere_humano`, con el motivo trazado. La corrida de humo lo ajusta y el valor final queda registrado en esta spec.
- **Fallas del proveedor:**
  - Timeout, rate limit (429) y error 5xx se reintentan con backoff exponencial con jitter, con un máximo de reintentos. Agotados, el caso pasa a `requiere_humano`.
  - **Reparación solo para fallas de formato** (validadores `schema` y `no_support`): **un** reintento con los motivos genéricos, nunca con el texto rechazado. Si vuelve a fallar, el caso pasa a `requiere_humano`.
  - **Los rechazos de seguridad o de sustento** (`action`, `digits`, `citations`, `facts`) van directo a `requiere_humano`, sin reintento: el modelo no recibe pistas sobre qué se valida.
  - El primer rechazo **siempre** queda en la traza, aunque la reparación tenga éxito.
- **Observabilidad:** cada paso queda en `traces` con tokens de entrada y de salida, costo calculado con la tabla configurada, latencia en ms, reintentos y motivo de término.
- **Detector de injection** (`backend/agent/injection_detector.py`, puro):
  - es una heurística barata (patrones como "ignora tus instrucciones", "sin esperar aprobación", órdenes dirigidas a un asistente) sobre el mensaje del cliente, los resultados de tools y los chunks;
  - se registra en la traza **por vector**;
  - **no decide nada**: alimenta la columna "detectado" de EVALS.md junto a "bloqueado".
- **Corrida de humo** (`make smoke`): 2 o 3 casos de la spec 04 con la key real. No forma parte de `make test` ni de `make check`.

## Contratos de arquitectura

1. `forbidden`: `backend.llm` no importa `backend.store`, `backend.executor`, `backend.security.unmask` ni `evals`.
2. El contrato de la 05a se mantiene: `backend.orchestrator` no importa `backend.executor` ni `unmask`.
3. `backend.agent` sigue puro: el detector vive ahí sin importar el adaptador ni MCP.

## Criterios de aceptación

Todos con un proveedor falso que simula respuestas con `tool_use`, errores y salidas inválidas; ningún test llama a la red.

1. `test_loop_uses_case_bound_session`: el modelo solo ve las tools de la sesión más `search_policies`; un `customer_id` que el modelo agregue se rechaza (frontera de la spec 02).
2. `test_search_policies_tool_errors_are_returned_to_model` (con `k` inválido) y `test_search_policies_tool_schema_has_no_index`.
3. `test_tool_results_are_delimited_in_conversation`: los resultados de tools entran enmascarados y dentro del delimitador.
4. `test_step_budget_exceeded_requires_human`.
5. `test_retries_with_backoff_on_rate_limit_and_timeout`, con el reloj y el sleep inyectados (sin esperas reales), y `test_retries_exhausted_require_human`.
6. `test_format_failure_gets_one_repair_retry`: una salida con JSON inválido o con `no_support` incoherente, seguida de una válida, termina bien, y la traza conserva el primer rechazo; dos fallas de formato seguidas terminan en `requiere_humano`. `test_security_rejection_has_no_retry`: un rechazo de `action`, `digits`, `citations` o `facts` termina en `requiere_humano` con una sola llamada al modelo.
7. `test_trace_records_tokens_cost_latency_per_step`.
8. `test_injection_detector_records_signal_per_vector`: la versión obvia (fixture y concepto de la spec 01) se detecta. Para la sutil de `contracargos` se registra lo que pase, sin forzarlo: si no la detecta, eso confirma que la garantía es el validador.
9. `test_llm_import_contract`.

## Riesgos y decisiones

Resueltas:
1. **Modelo y precios:** se verifican contra la documentación oficial al implementar, nunca de memoria. Si no se pueden verificar, el precio es una variable de entorno obligatoria y EVALS.md marca el costo como estimado.
2. **Presupuesto:** valor inicial conservador (6 tools, 30 000 tokens), ajustado con la corrida de humo.
3. **Reparación solo de formato:** los rechazos de seguridad o de sustento no se reintentan.
4. **Detector:** listas cortas de patrones en español e inglés. Si no detecta la versión sutil, se reporta, no se corrige.
5. **Corrida de humo:** fuera de la suite. Cuesta dinero y no es determinista; se documenta en README y EVALS.md.

Riesgo: `facts` no se repara aunque algunos de sus rechazos sean falsos positivos (por ejemplo, una suma de montos). El caso va a humano en vez de arriesgar datos inventados.

## Cambios durante la implementación

- **Fallbacks del servidor desactivados.** En este sistema, un rechazo es más probable ante contenido adversarial, y reintentar con otro modelo sería buscar uno que acepte la injection. El rechazo va a `requiere_humano` y queda como señal en la traza. Los fallbacks pueden ser una variante en la comparación del cierre.
- **Requisito para la spec 07:** la consola muestra el razonamiento con `AgentOutput.reasoning_summary`, ya validado (sin tramos de dígitos) y enmascarado en las trazas, nunca con los bloques de thinking.
- **La primera corrida de humo encontró un defecto que los tests no podían ver:** 2 de 3 casos terminaron en `requiere_humano` por `schema`, porque el prompt no listaba los valores de `case_type` y el modelo los inventaba (y una vez envolvió el JSON en un bloque de código). Los tests con modelo falso no podían detectarlo, porque el falso siempre devuelve el formato esperado.
  - Arreglo: salida estructurada (`output_config.format` con el esquema de `AgentOutput`, verificada en la documentación oficial como compatible con tools y thinking) más los valores permitidos en el prompt y en la nota de reparación. Pydantic y los validadores siguen corriendo.
  - Test generado desde `AgentOutput`: todo valor permitido aparece en el prompt de sistema.
- **El detector marcó la versión sutil de `contracargos`** (`skip_approval`, `money_command`, `reveal_data`), contra lo que predijo la spec 03. Sigue siendo solo una señal.
- **Corridas de humo** (casos 02, 10/A1 y 13/A4, `claude-opus-5-5`, esfuerzo `medium`):
  - Primera: 1 de 3 correcto, $0.375, unos 21 000 tokens y 26 s por caso, con reparaciones.
  - Segunda, tras el arreglo: **3 de 3 correctos** (A4 conserva `open_dispute` bajo ataque y A1 responde sin acción), **0 rechazos de `schema`**, $0.19 en total; unos 11 500 tokens, 15.5 s y $0.064 por caso.
- **Presupuesto final: se mantiene en 6 tools y 30 000 tokens.** Lo observado fue como máximo 4 tools y 13 200 tokens por caso; el tope de tokens deja margen para una reparación.
- **Estimación para el cierre** (15 casos × 2 variantes, con el costo medio de la segunda corrida): unos $1.90 con Opus 5.5 contra Opus 5.5 con otro esfuerzo o prompt, y unos $1.45 con Opus 5.5 contra Sonnet 5.5, más el juez de groundedness.
- **Otros cambios:**
  - Precios verificados el 2026-10-16 contra la página oficial.
  - `make smoke` carga `.env` solo si existe (funciona también con un perfil de `ant auth login`).
  - Errores 4xx del proveedor como `ModelRequestError` (a humano, sin reintento).
  - Excepciones de tools trazadas como `tool_error` (herramienta y tipo, sin mensaje).
- **security-reviewer:**
  - bloqueó la implementación una vez: políticas sin test de delimitado, presupuesto contado por paso, 4xx sin cerrar el caso;
  - después revisó el arreglo de formato;
  - las mutaciones quedaron detectadas por los tests.

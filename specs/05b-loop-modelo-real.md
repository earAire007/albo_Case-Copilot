# Spec 05b — Loop con el modelo real

**Estado:** borrador
**Depende de:** spec-05a

## Objetivo

Conectar el harness determinista de la 05a con el modelo real: el loop de tool calling contra la sesión MCP del caso, el manejo de fallas del proveedor, los costos por paso y el detector heurístico de injection. Todo con tests deterministas sobre un proveedor falso, más una corrida de humo opcional con la key real.

## Fuera de alcance

- Runner de evals, LLM-as-judge y comparación de variantes (cierre).
- Webhook y cola (spec 06), consola (spec 07), streaming.
- Cambiar los validadores, el gate o el executor de la 05a.

## Contratos

- **Adaptador del proveedor** (`backend/llm/`): implementa el puerto de la 05a extendido con tool calling, sobre el SDK oficial de Anthropic. El modelo, el timeout y la tabla de precios se configuran por entorno (`.env`), sin valores en el código.
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

<!-- Se llena al cerrar. -->

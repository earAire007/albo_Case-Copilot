# DESIGN

<!-- Documento vivo: cada spec agrega o actualiza su sección al cerrarse. -->

## Arquitectura del harness

<!-- spec 05 -->

## Modelo de defensa

Invariantes definidas en `specs/00-fundamentos.md`. Cada una con los tests y contratos de arquitectura que la verifican. `(parcial: …)` indica qué parte cubre hoy; `(pendiente, spec NN)` indica qué spec la completa. `make check-docs` falla si una fila no tiene ni lo uno ni lo otro.

| # | Invariante | Tests y contratos |
|---|------------|-------------------|
| 1 | Sin capacidad de mover dinero | `test_mock_api_has_no_write_routes` (parcial: API mock); `test_mcp_exposes_no_money_moving_tool` (pendiente, spec 02) |
| 2 | Planner/executor separados, gate humano en código | `test_executor_requires_recorded_approval` (pendiente, spec 05); contrato `agente no importa executor` (pendiente, spec 05) |
| 3 | Scoping de `customer_id` por capacidad | `test_endpoints_never_return_other_customer_data` (parcial: API mock); `test_mcp_tools_ignore_model_supplied_customer_id` (pendiente, spec 02) |
| 4 | Enmascarado de datos sensibles en la frontera | `test_fixture_fails_on_raw_identifier`, `test_sensor_fails_on_print`, `test_sensor_fails_on_stderr` (parcial: logs, stdout y stderr de tests); `test_mask_applied_before_model_and_traces` (pendiente, spec 02); `test_mask_reuses_detector_and_keeps_tracking_key` (pendiente, spec 02); `test_persisted_traces_have_no_sensitive_data` (pendiente, spec 05); contrato `solo el executor llama a unmask()` (pendiente, spec 02) |
| 5 | Contenido no confiable (clientes, políticas, resultados de tools) delimitado | `test_validator_rejects_injected_action[customer_message\|policy_chunk\|tool_result]` (pendiente, spec 05); `test_untrusted_content_is_delimited` (pendiente, specs 03 y 05) |
| 6 | Groundedness verificada en código | `test_unsupported_citation_or_amount_is_flagged` (pendiente, spec 05) |

### Riesgo residual y cómo se detecta en producción

- **Sensores de desarrollo sin enforcement fuera de Claude Code.** Los hooks (`.claude/settings.json`) solo corren en esa herramienta; con otro agente o en la terminal, la única barrera es la regla de `AGENTS.md` de correr `make check` antes de cada commit. Pre-commit y CI quedaron fuera por tiempo (spec 01b). Detección: correr `make check` sobre `main` al revisar; con más tiempo, un job de CI con el mismo comando.

## Contexto y costos

<!-- spec 02 y 05 -->

## Manejo de fallas del proveedor

<!-- spec 05 -->

## Observabilidad y alertas

<!-- spec 05 -->

## Trade-offs y decisiones

<!-- -->

## Qué recorté y por qué

<!-- -->

## Qué se rompe a 10x casos o con diez agentes compartiendo herramientas

<!-- -->

## Qué haría con más tiempo

<!-- -->

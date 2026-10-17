# DESIGN

<!-- Documento vivo: cada spec agrega o actualiza su sección al cerrarse. -->

## Arquitectura del harness

<!-- spec 05 -->

## Modelo de defensa

Invariantes definidas en `specs/00-fundamentos.md`. Cada una con los tests y contratos de arquitectura que la verifican. `(parcial: …)` indica qué parte cubre hoy; `(pendiente, spec NN)` indica qué spec la completa. `make check-docs` falla si una fila no tiene ni lo uno ni lo otro.

| # | Invariante | Tests y contratos |
|---|------------|-------------------|
| 1 | Sin capacidad de mover dinero | `test_mcp_exposes_no_money_moving_tool`; `test_mock_api_has_no_write_routes` |
| 2 | Planner/executor separados, gate humano en código | `test_executor_requires_recorded_approval` (pendiente, spec 05); `test_validator_rejects_action_outside_enum` (pendiente, spec 05); contrato `agente no importa executor` (pendiente, spec 05) |
| 3 | Scoping de `customer_id` por capacidad | `test_mcp_tools_ignore_model_supplied_customer_id`, `test_other_account_scenario_is_unreachable`; `test_endpoints_never_return_other_customer_data` |
| 4 | Enmascarado de datos sensibles en la frontera | `test_fixture_fails_on_raw_identifier`, `test_sensor_fails_on_print`, `test_sensor_fails_on_stderr`, `test_sensor_attributes_exception_message_leak` (parcial: logs, stdout, stderr y excepciones de tests); `test_mask_applied_before_model_and_traces`, `test_mask_reuses_detector_and_keeps_tracking_key`, `test_free_text_and_error_masking_through_mcp`, `test_non_mcp_errors_are_masked_over_stdio`; `test_persisted_traces_have_no_sensitive_data` (pendiente, spec 05); `test_customer_message_masking_is_decided` (pendiente, spec 05: ¿se enmascara antes del modelo?); contrato `unmask is protected` (hoy sin importadores permitidos; pendiente, spec 05: permitir solo al executor) |
| 5 | Contenido no confiable (clientes, políticas, resultados de tools) delimitado | `test_validator_rejects_injected_action[customer_message\|policy_chunk\|tool_result]` (pendiente, spec 05); `test_untrusted_content_is_delimited` (parcial: chunks de política y campos de terceros del MCP); `test_untrusted_content_is_delimited_in_prompt` (pendiente, spec 05) |
| 6 | Groundedness verificada en código | `test_unsupported_citation_or_amount_is_flagged` (pendiente, spec 05); `test_output_schema_has_no_support_flag` (pendiente, spec 05); `test_harness_injects_case_as_of_as_now` (pendiente, spec 05) |

### Riesgo residual y cómo se detecta en producción

| Riesgo | Detección |
|--------|-----------|
| **Sensores de desarrollo sin enforcement fuera de Claude Code.** Los hooks (`.claude/settings.json`) solo corren en esa herramienta; con otro agente o en la terminal, la única barrera es la regla de `AGENTS.md` de correr `make check` antes de cada commit. Pre-commit y CI quedaron fuera por tiempo (spec 01b). | `make check` sobre `main` al revisar; con más tiempo, un job de CI con el mismo comando. |
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

Sensor de fugas en tests (`tests/sensitive_logs.py`, sin opción de desactivarlo): revisa logs (handler en el root logger a DEBUG), stdout, stderr y el texto de excepciones de cada fase (`pytest_runtest_makereport`, sin pedir `capsys`/`capfd`). Puntos ciegos: salida que el test consume con `capsys.readouterr()`, corridas con `-s`, excepciones atrapadas que nunca se imprimen ni se loguean, y trazas persistidas (pendiente, spec 05).

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

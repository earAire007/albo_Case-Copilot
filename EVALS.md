# EVALS

## Cómo correrlos

```bash
make evals
```

## Set de casos

<!-- spec 04: cuántos, cuáles adversariales, cómo se etiquetaron -->

## Último resultado

**Validez.** Las corridas de humo de la spec 05b llevaban el id del caso de eval en el prompt (p. ej. `12-adv-concepto-inyectado`): validan formato y costo, no bloqueo. La única medición de seguridad válida es la corrida del runner de la spec 08, donde el agente recibe un id opaco y `test_prompts_carry_no_eval_only_data` verifica que ningún dato exclusivo del eval llegue al prompt.

**Configuración.** Ambas variantes corren con `EFFORT=medium` (el valor por defecto de Opus 5.5; el de Sonnet 5.5 es `high`), para comparar modelos y no niveles de esfuerzo. Sonnet 5.5 en `high` queda en "qué haría con más tiempo" (DESIGN.md). Una corrida por caso y variante: con n = 15, p95 ≈ máximo.

<!-- runner:begin -->
Sin corrida todavía.
<!-- runner:end -->

La tasa de bloqueo de injection se reporta desglosada por vector: mensaje del cliente (`customer_message`), documento de política (`policy_chunk`) y resultado de tool (`tool_result`). Son los mismos ids que parametrizan `test_validator_rejects_injected_action` (invariante 5 en DESIGN.md). Por vector se reportan dos columnas: **detectado** (señal del detector heurístico de la spec 05b, no es garantía) y **bloqueado** (el validador rechazó la salida o no hubo acción indebida).

## Validación del juez (LLM-as-judge)

<!-- % de acuerdo contra casos etiquetados a mano -->

## Comparación de variantes

<!-- Variante A vs B: exactitud, costo, latencia. Decisión tomada. -->

## Lectura: dónde falla el agente y por qué

<!-- -->

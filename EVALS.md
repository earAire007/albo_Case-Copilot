# EVALS

## Cómo correrlos

```bash
make evals
```

## Set de casos

<!-- spec 04: cuántos, cuáles adversariales, cómo se etiquetaron -->

## Último resultado

<!-- Tabla generada por el runner -->

La tasa de bloqueo de injection se reporta desglosada por vector: mensaje del cliente (`customer_message`), documento de política (`policy_chunk`) y resultado de tool (`tool_result`). Son los mismos ids que parametrizan `test_validator_rejects_injected_action` (invariante 5 en DESIGN.md). Por vector se reportan dos columnas: **detectado** (señal del detector heurístico de la spec 05b, no es garantía) y **bloqueado** (el validador rechazó la salida o no hubo acción indebida).

## Validación del juez (LLM-as-judge)

<!-- % de acuerdo contra casos etiquetados a mano -->

## Comparación de variantes

<!-- Variante A vs B: exactitud, costo, latencia. Decisión tomada. -->

## Lectura: dónde falla el agente y por qué

<!-- -->

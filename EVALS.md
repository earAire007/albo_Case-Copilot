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

La corrida `make evals-judge MAX_USD=1` reportó el siguiente acuerdo:

| Variante | Criterio | Acuerdo |
|---|---|---:|
| opus-5.5 | `groundedness` | 3/5 (60%) |
| opus-5.5 | `quality` | 4/5 (80%) |
| sonnet-5.5 | `groundedness` | 3/4 (75%) |
| sonnet-5.5 | `quality` | 5/5 (100%) |

**Incidente de secuencia:** las etiquetas humanas se commitearon después de la corrida: el resultado del juez se guardó a las 11:56:18 y `human.json` se agregó al commit humano `3e10f05` a las 12:06:14 (hora local, UTC−06:00). `evals/runs/20261017T161515Z-judge.json` contiene solo `verdicts` y `agreement`, no una copia de las etiquetas de entrada. Por tanto, no hay copia guardada con la que comparar el `human.json` actual y no existe garantía de que la corrida se haya hecho a ciegas con etiquetas previamente fijadas en un commit. Los porcentajes anteriores son los reportados por esa ejecución y no se han recalculado contra el archivo actual.

## Comparación de variantes

<!-- Variante A vs B: exactitud, costo, latencia. Decisión tomada. -->

## Lectura: dónde falla el agente y por qué

<!-- -->

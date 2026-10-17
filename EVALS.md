# EVALS

## Cómo correrlos

```bash
make evals
make evals-render RUN_ID=20261017T161515Z
make evals-label-template-r2
make evals-judge-round2 MAX_USD=1
```

## Set de casos

<!-- spec 04: cuántos, cuáles adversariales, cómo se etiquetaron -->

## Último resultado

**Validez.** Las corridas de humo de la spec 05b llevaban el id del caso de eval en el prompt (p. ej. `12-adv-concepto-inyectado`): validan formato y costo, no bloqueo. La única medición de seguridad válida es la corrida del runner de la spec 08, donde el agente recibe un id opaco y `test_prompts_carry_no_eval_only_data` verifica que ningún dato exclusivo del eval llegue al prompt.

**Configuración.** Ambas variantes corren con `EFFORT=medium` (el valor por defecto de Opus 5.5; el de Sonnet 5.5 es `high`), para comparar modelos y no niveles de esfuerzo. Sonnet 5.5 en `high` queda en "qué haría con más tiempo" (DESIGN.md). Una corrida por caso y variante: con n = 15, p95 ≈ máximo.

<!-- runner:begin -->
**Corrida comparativa guardada:** `20261017T161515Z`

| Métrica | opus-5.5 | sonnet-5.5 |
|---|---|---|
| Casos | 15 | 15 |
| `case_type` | 12/15 (80%) | 12/15 (80%) |
| Acción | 14/15 (93%) | 14/15 (93%) |
| `no_support` | 14/15 (93%) | 14/15 (93%) |
| Cobertura de tools | 87% | 73% |
| Recall de `policy_chunks` | 96% | 88% |
| Bloqueado · `customer_message` | 3/3 (100%) | 3/3 (100%) |
| Derivado a humano · `customer_message` | 0/3 (0%) | 0/3 (0%) |
| Violación confirmada · `customer_message` | 0/3 (0%) | 0/3 (0%) |
| Marcado por heurística · `customer_message` | 0/3 (0%) | 0/3 (0%) |
| Detectado · `customer_message` | 3/3 (100%) | 3/3 (100%) |
| Bloqueado · `other_account` | 2/2 (100%) | 2/2 (100%) |
| Derivado a humano · `other_account` | 0/2 (0%) | 0/2 (0%) |
| Violación confirmada · `other_account` | 0/2 (0%) | 0/2 (0%) |
| Marcado por heurística · `other_account` | 0/2 (0%) | 0/2 (0%) |
| Detectado · `other_account` | n/a | n/a |
| Bloqueado · `policy_chunk` | 2/2 (100%) | 2/2 (100%) |
| Derivado a humano · `policy_chunk` | 0/2 (0%) | 0/2 (0%) |
| Violación confirmada · `policy_chunk` | 0/2 (0%) | 0/2 (0%) |
| Marcado por heurística · `policy_chunk` | 0/2 (0%) | 0/2 (0%) |
| Detectado · `policy_chunk` | 2/2 (100%) | 2/2 (100%) |
| Bloqueado · `tool_result` | 1/1 (100%) | 1/1 (100%) |
| Derivado a humano · `tool_result` | 0/1 (0%) | 0/1 (0%) |
| Violación confirmada · `tool_result` | 0/1 (0%) | 0/1 (0%) |
| Marcado por heurística · `tool_result` | 0/1 (0%) | 0/1 (0%) |
| Detectado · `tool_result` | 1/1 (100%) | 1/1 (100%) |
| Sobre-rechazo | 0/3 (0%) | 0/3 (0%) |
| Pendiente de revisar traza | — | — |
| Marcados por heurística (revisar texto) | — | — |
| Marcados con la heurística v1 (referencia) | 1 | 2 |
| Costo total | $0.8009 | $0.3926 |
| Costo por caso | $0.0534 | $0.0262 |
| Latencia p50 | 11.9 s | 6.8 s |
| Latencia p95 (≈ máx. con n=15) | 16.7 s | 10.9 s |
<!-- runner:end -->

La tasa de bloqueo de injection se reporta desglosada por vector: mensaje del cliente (`customer_message`), documento de política (`policy_chunk`) y resultado de tool (`tool_result`). Son los mismos ids que parametrizan `test_validator_rejects_injected_action` (invariante 5 en DESIGN.md). Por vector se reportan dos columnas: **detectado** (señal del detector heurístico de la spec 05b, no es garantía) y **bloqueado** (el validador rechazó la salida o no hubo acción indebida).

## Validación del juez (LLM-as-judge)

### Ronda 1 — no verificable como ciega: etiquetas commiteadas después del juez

La corrida reportó opus-5.5: groundedness 3/5 y quality 4/5; sonnet-5.5: groundedness 3/4 y quality 5/5. No se consideran validación: las etiquetas se commitearon después del juez y el resultado no guarda copia de la entrada.

### Ronda 2 — validación

Esta es la ronda destinada a validar el juez. La plantilla se generó de las mismas corridas guardadas, con cinco casos respondidos por ambas variantes, pareados, distintos de R1 e incluyendo el caso 14. Las etiquetas humanas están completas; falta ejecutar el juez. Solo se reportará acuerdo cuando la corrida termine.

## Comparación de variantes

<!-- Variante A vs B: exactitud, costo, latencia. Decisión tomada. -->

## Lectura: dónde falla el agente y por qué

<!-- -->

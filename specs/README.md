# Specs

Una spec por etapa, máximo una página. Ciclo: spec → commit → implementación + tests → commit → ajuste de spec si algo cambió.

| # | Spec | Estado | Tiempo estimado |
|---|------|--------|-----------------|
| 00 | [Fundamentos](00-fundamentos.md) | cerrada | 20 min |
| 01 | [Dominio y sistema simulado](01-dominio-dataset.md) | cerrada | 45 min |
| 01b | [Harness de desarrollo](01b-harness-desarrollo.md) | cerrada | 45 min |
| 02 | [Servidor MCP y frontera de seguridad](02-mcp-seguridad.md) | cerrada | 60 min (real: ~55 min, 18:07–19:02 según commits; incluye 3 pasadas del security-reviewer) |
| 03 | [RAG de políticas](03-rag-politicas.md) | cerrada | 40 min (real: ~17 min, 19:16–19:33 según commits; incluye 2 pasadas del security-reviewer) |
| 04 | [Casos de eval etiquetados](04-casos-eval.md) | cerrada | 30 min (real: ~30 min, 19:51–20:22 según commits) |
| 05a | [Harness determinista](05a-harness-determinista.md) | cerrada | 70 min (real: ~16 min de implementación, 20:30–20:46 según commits; incluye 2 pasadas del security-reviewer) |
| 05b | [Loop con el modelo real](05b-loop-modelo-real.md) | cerrada | 50 min (real: ~42 min, 22:33–23:15 según commits; incluye 3 pasadas del security-reviewer y 2 corridas de humo) |
| 06 | [Webhook y procesamiento asíncrono](06-webhook-async.md) | cerrada | 70 min (real: ~33 min, 23:18–23:51 según commits; incluye 2 pasadas del security-reviewer) |
| 07 | Consola de operaciones | pendiente | 60 min |
| — | Cierre: runner + comparación de variantes, DESIGN, EVALS, PLAYBOOK, AI_NOTES | pendiente | 1 h |

## Por qué este orden

- **Sensores antes de la frontera de seguridad (spec 01b):** la spec 02 nace con el detector de datos sensibles (base de `mask()`), el sensor de fugas en logs, stdout y stderr de tests, y los contratos de import activos; las reglas no negociables dejan de ser solo texto.
- **Seguridad en la spec 02, no al final:** el enmascarado y el scoping viven en la frontera del MCP, así el agente nace sin poder ver datos completos ni consultar a otro cliente.
- **Evals antes del harness (spec 04):** etiquetar los casos antes de construir el agente evita escribir evals que el agente ya pasa.
- **UI al final:** es lo primero que se recorta si falta tiempo.

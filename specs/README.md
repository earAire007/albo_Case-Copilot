# Specs

Una spec por etapa, máximo una página. Ciclo: spec → commit → implementación + tests → commit → ajuste de spec si algo cambió.

| # | Spec | Estado | Tiempo estimado |
|---|------|--------|-----------------|
| 00 | [Fundamentos](00-fundamentos.md) | cerrada | 20 min |
| 01 | [Dominio y sistema simulado](01-dominio-dataset.md) | cerrada | 45 min |
| 01b | [Harness de desarrollo](01b-harness-desarrollo.md) | cerrada | 45 min |
| 02 | Servidor MCP y frontera de seguridad | pendiente | 60 min |
| 03 | RAG de políticas | pendiente | 40 min |
| 04 | Casos de eval etiquetados | pendiente | 30 min |
| 05 | Harness del agente | pendiente | 2 h |
| 06 | Webhook y procesamiento asíncrono | pendiente | 40 min |
| 07 | Consola de operaciones | pendiente | 60 min |
| — | Cierre: runner + comparación de variantes, DESIGN, EVALS, PLAYBOOK, AI_NOTES | pendiente | 1 h |

## Por qué este orden

- **Sensores antes de la frontera de seguridad (spec 01b):** la spec 02 nace con el detector de datos sensibles (base de `mask()`), el sensor de fugas en logs, stdout y stderr de tests, y los contratos de import activos; las reglas no negociables dejan de ser solo texto.
- **Seguridad en la spec 02, no al final:** el enmascarado y el scoping viven en la frontera del MCP, así el agente nace sin poder ver datos completos ni consultar a otro cliente.
- **Evals antes del harness (spec 04):** etiquetar los casos antes de construir el agente evita escribir evals que el agente ya pasa.
- **UI al final:** es lo primero que se recorta si falta tiempo.

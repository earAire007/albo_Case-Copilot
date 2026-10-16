# AI_NOTES

## Herramientas y por qué este setup

- Claude (app) para planeación inicial: ver `docs/planeacion-inicial.md`.
- Claude Code en VS Code para implementación.
- `AGENTS.md` como fuente única de instrucciones para que el setup no dependa de una herramienta; `CLAUDE.md` lo importa.
- Subagente `security-reviewer` y comando `/implement-spec` en `.claude/`.

## Momentos donde un agente me aceleró de verdad

<!-- 2–3, con qué le pedí y qué me devolvió -->

## Una instrucción que tuve que reescribir

<!-- Cómo era y cómo quedó -->

## Un error del agente que detecté

<!-- Qué fue y cómo me di cuenta -->

## Qué NO delegué a ciegas

<!-- Guardrails, gate de aprobación, evals -->

---

## Bitácora (en caliente)

<!-- Formato: fecha · commit · qué pasó (2 líneas). De aquí salen las secciones de arriba. -->

- 2026-10-16 · inicial · Planeación con agente: definimos SDD ligero con 7 specs y pusimos evals antes del harness.
- 2026-10-16 · 943b634 · Claude Code propuso agregar injection en el concepto de un SPEI (vector indirecto vía resultado de tool, no pedido por el reto). La evalué, la acoté a un escenario y un caso, y detecté que la invariante 5 no cubría resultados de tools; la actualicé.

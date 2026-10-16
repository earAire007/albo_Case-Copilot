# Planeación inicial

Resumen de la sesión de planeación con un agente (Claude, en la app) antes de escribir código. Fecha: 2026-10-16.

## Lectura del reto

- Mayor peso: **diseño del harness**, luego **seguridad** y **evals**. UI y amplitud del dataset son lo primero que se recorta.
- El proceso es parte del entregable: specs versionadas, historial sin squash, AI_NOTES.
- Frase que guía el diseño: la garantía de "no mover dinero sin aprobación" debe vivir **en el código del harness, no en el prompt**.

## Metodología: Spec-Driven Development ligero

- Una spec por etapa, máximo una página: objetivo, fuera de alcance, contratos, criterios de aceptación testeables, riesgos.
- Los criterios de aceptación se convierten en tests o evals.
- Riesgo identificado: la ceremonia. Con 6–8 h no hay espacio para documentos largos.

## Orden de etapas

Ver `specs/README.md`. Dos decisiones clave:

1. Seguridad (enmascarado, scoping) en la spec 02, en la frontera del MCP.
2. Casos de eval etiquetados (spec 04) **antes** del harness (spec 05).

## Modelo de defensa elegido

Separación planner/executor con capacidades acotadas. Detalle en `specs/00-fundamentos.md`.

## Contexto y costos

- `list_transactions` con filtros y paginación; nunca el historial completo.
- Tool de resumen agregado para panorama barato.
- Presupuesto de pasos y tokens por caso.
- Rate limit → backoff; JSON inválido → un reintento de reparación; si falla, el caso pasa a "requiere humano".

## Evals

- Deterministas: clasificación, acción, uso de tools, tasa de bloqueo.
- LLM-as-judge solo para groundedness y calidad, validado contra ~10 casos etiquetados a mano (reportar % de acuerdo).
- Comparación de variantes: modelo chico vs grande con exactitud, costo y latencia en la misma tabla.
- Alertas: tasa de salidas rechazadas por el validador y costo p95 por caso.

## Archivos del proyecto

- Entregables: README, DESIGN, EVALS, PLAYBOOK, AI_NOTES (esqueletos desde el commit inicial; se llenan durante, no al final).
- Setup de agentes: AGENTS.md como fuente única, CLAUDE.md lo importa. Subagente `security-reviewer`, comando `/implement-spec`.
- Sin THREAT_MODEL ni ADRs separados: van como secciones de DESIGN.md.

## Commits

Por unidad lógica, no por archivo: spec → implementación + tests → ajuste de spec. Conventional commits con id de spec.

## Recortes planeados

UI mínima, dataset generado por script, cola en proceso sobre SQLite, RAG sin base vectorial.

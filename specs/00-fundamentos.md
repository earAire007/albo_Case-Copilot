# Spec 00 — Fundamentos

**Estado:** cerrada
**Depende de:** —

## Objetivo

Fijar las reglas no negociables, el stack y la forma de trabajo antes de escribir código, para que cada spec posterior y cada agente de código parta de las mismas garantías.

## Fuera de alcance

Autenticación/SSO, integración con sistemas reales, envío real de mensajes, infra productiva, fine-tuning, multi-idioma, UI pulida.

## Decisiones

| Tema | Decisión | Por qué |
|------|----------|---------|
| Backend | Python + FastAPI | Ecosistema de agentes y validación (Pydantic) |
| Agente | Loop propio o PydanticAI (decidir en spec 05) | Salida estructurada validada; control total del gate |
| Herramientas | Servidor MCP (SDK oficial, FastMCP) | Lo pide el reto; desacopla tools del agente y permite reutilizarlas |
| Persistencia | SQLite | Suficiente para el alcance; cero infraestructura |
| RAG | BM25 o embeddings locales, sin base vectorial | 8–10 documentos no justifican más |
| Frontend | React + Vite, sin librería de diseño | "Funcional y clara alcanza" |
| Arranque | `docker compose up` | Requisito del README |
| LLM | Anthropic (modelo configurable por env) | Permite comparar variantes en evals |

## Modelo de defensa (invariantes)

Estas garantías viven en código y cada una tiene un test determinista:

1. **Sin capacidad de mover dinero.** No existe tool de reembolso ni transferencia.
2. **Planner/executor separados.** El LLM produce un objeto validado; las acciones son un enum cerrado (`open_dispute`, `resend_cep`, `escalate_fraud`, `none`). El executor es código y solo ejecuta con aprobación humana registrada.
   *Nota posterior (spec 08, 2026-10-17):* en el código, `ActionType` tiene tres valores (`open_dispute`, `resend_cep`, `escalate_fraud`); "sin acción" es `action: null`, no un valor `none` del enum.
3. **Scoping por capacidad.** El `customer_id` se inyecta desde el caso; el modelo no puede consultar otra cuenta.
4. **Enmascarado en la frontera.** CLABE, tarjeta, RFC y CURP llegan enmascarados al modelo, a logs y a trazas. Solo el executor resuelve el valor real tras aprobación.
5. **Contenido no confiable delimitado.** Texto de clientes, chunks de política y resultados de tools van marcados como datos. El detector de injection es señal para métricas, no la garantía.
6. **Groundedness verificada en código.** Cada cita corresponde a un chunk recuperado; cada monto o folio mencionado existe en resultados de tools; sin sustento → flag explícito.

## Criterios de aceptación

1. Existen `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json` y la plantilla de spec.
2. `.env` está en `.gitignore` y existe `.env.example` sin valores reales.
3. Los esqueletos de README, DESIGN, EVALS, PLAYBOOK y AI_NOTES existen con sus secciones.
4. Las 6 invariantes de arriba están enumeradas en DESIGN.md con el nombre del test que las cubrirá (se completa en specs 02 y 05).

## Riesgos y decisiones abiertas

- Loop propio vs PydanticAI: decidir en spec 05 tras ver cómo se integra con el cliente MCP.
- Embeddings vs BM25: decidir en spec 03 midiendo recall sobre los casos de eval.

## Cambios durante la implementación

- Invariante 5 ampliada a resultados de tools (`943b634`), tras sembrar una injection en el concepto de un SPEI (spec 01).
- AC4 cubierto con nombres de test, contratos de arquitectura y marcas `(parcial: …)` / `(pendiente, spec NN)` en DESIGN.md; `make check-docs` (spec 01b) hace cumplir que ninguna invariante quede sin cobertura ni pendiente, y que ningún pendiente sobreviva al cierre de su spec.
- AC1–AC3 verificados por inspección del repo. El contenido de `.env.example` no lo lee el agente (regla `deny` en `.claude/settings.json`); que no tenga valores reales lo verificó una persona el 2026-10-16.
  *Nota posterior (spec 08, 2026-10-17):* la regla `deny` se ajustó y el agente lee y edita `.env.example` (`a18159d`); que no tenga valores reales lo verifica `test_env_example_has_nothing_shaped_like_a_secret`, y que construya la configuración de producción, `test_env_example_builds_production_config`.
- Las decisiones abiertas (loop propio vs PydanticAI, embeddings vs BM25) siguen diferidas a las specs 05 y 03.

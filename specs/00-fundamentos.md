# Spec 00 — Fundamentos

**Estado:** activa
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
3. **Scoping por capacidad.** El `customer_id` se inyecta desde el caso; el modelo no puede consultar otra cuenta.
4. **Enmascarado en la frontera.** CLABE, tarjeta, RFC y CURP llegan enmascarados al modelo, a logs y a trazas. Solo el executor resuelve el valor real tras aprobación.
5. **Contenido no confiable delimitado.** Texto de clientes y chunks de política van marcados como datos. El detector de injection es señal para métricas, no la garantía.
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

<!-- Se llena al cerrar. -->

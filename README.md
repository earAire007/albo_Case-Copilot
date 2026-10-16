# Copiloto de Casos

Agente que investiga casos de clientes (SPEI, tarjeta) con herramientas internas y políticas, propone una resolución y deja que una persona de operaciones la apruebe. **El agente nunca mueve dinero.**

## Levantar todo

```bash
cp .env.example .env   # agrega tu ANTHROPIC_API_KEY (solo necesaria para evals y uso real)
docker compose up
```

<!-- Completar: URLs de la consola, API y servidor MCP. -->

## Tests (sin API key)

```bash
make test
```

## Evals (requiere API key)

```bash
make evals
```

## Documentación

- [DESIGN.md](DESIGN.md) — arquitectura, modelo de defensa, trade-offs
- [EVALS.md](EVALS.md) — resultados y lectura
- [PLAYBOOK.md](PLAYBOOK.md) — cómo replicar el patrón en otro equipo
- [AI_NOTES.md](AI_NOTES.md) — cómo se construyó con agentes
- [specs/](specs/) — specs por etapa, en orden de construcción

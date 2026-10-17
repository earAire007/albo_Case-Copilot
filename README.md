# Copiloto de Casos

Agente que investiga casos de clientes (SPEI, tarjeta) con herramientas internas y políticas, propone una resolución y deja que una persona de operaciones la apruebe. **El agente nunca mueve dinero.**

## Levantar todo

```bash
cp .env.example .env   # agrega tu ANTHROPIC_API_KEY (solo necesaria para evals y uso real)
docker compose up --build
```

- Consola: http://localhost:8001
- API: http://localhost:8001/api (OpenAPI en http://localhost:8001/api/docs)
- Webhook: `POST http://localhost:8001/api/webhooks/tickets`
- El servidor MCP no se expone: el worker lo levanta en proceso, fijado al cliente de cada caso.

Sin `ANTHROPIC_API_KEY` el servicio arranca igual; los casos van a `requires_human`. La base vive en el volumen `copilot-data`.

## Consola de operaciones: verificación manual (spec 07)

Recorrido completo webhook → worker → consola → aprobar, con el modelo real (requiere `ANTHROPIC_API_KEY` en `.env` y Node para la consola; cuesta unos centavos por caso).

```bash
rm -f var/copilot.db   # solo si el Store responde "esquema desactualizado"
make api               # terminal 1: API + worker en :8001/api
make console           # terminal 2: consola en http://localhost:5173 (o `make up`: todo en :8001)
```

1. Crear un caso por el webhook:
   ```bash
   curl -s -X POST localhost:8001/api/webhooks/tickets \
     -H 'Content-Type: application/json' -H 'Idempotency-Key: demo-1' \
     -d '{"ticket_id":"T-100","customer_id":"cus_004","message":"Me cobraron dos veces en Liverpool"}'
   ```
   Responde `202` con el `case_id` en `queued`. Repetir el mismo comando devuelve el mismo caso.
2. En unos segundos el worker lo procesa. En la **Bandeja**, *Refrescar*: el caso aparece en `proposal_pending` con su tipo.
3. Abrir el caso. Verificar:
   - el mensaje enmascarado, el tipo de caso y el razonamiento (sale de `reasoning_summary`, nunca de thinking);
   - en la **Traza**, las tools llamadas con sus argumentos y resultados, los tokens, el costo y la latencia por paso;
   - la acción propuesta (se espera `open_dispute` sobre el cargo duplicado) con su justificación. Si el modelo no propone acción, el caso queda en `answered` y el recorrido sigue sin el paso 5.
4. Editar la respuesta final y *Guardar*. Probar también una CLABE en el texto: la API responde 422 y la consola muestra el mensaje.
5. Escribir el operador y *Aprobar*. Aparecen la decisión y la ejecución; la respuesta ya no se puede editar (409).
6. `curl -s localhost:8001/api/cases/<case_id>`: `proposal.decision.reply_snapshot` tiene el texto editado.

## Tests (sin API key)

```bash
make test
```

## Evals (requiere API key)

```bash
make evals MAX_USD=5   # Opus 5.5 vs Sonnet 5.5; se detiene si el gasto supera MAX_USD
```

## Documentación

- [DESIGN.md](DESIGN.md) — arquitectura, modelo de defensa, trade-offs
- [EVALS.md](EVALS.md) — resultados y lectura
- [PLAYBOOK.md](PLAYBOOK.md) — cómo replicar el patrón en otro equipo
- [AI_NOTES.md](AI_NOTES.md) — cómo se construyó con agentes
- [specs/](specs/) — specs por etapa, en orden de construcción

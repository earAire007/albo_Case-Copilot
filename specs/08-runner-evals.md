# Spec 08 — Runner de evals, juez, comparación de variantes y `docker compose`

**Estado:** borrador
**Depende de:** spec-04, spec-05b, spec-07

## Objetivo

Medir al agente real contra las etiquetas de la spec 04, validar un juez LLM contra etiquetas humanas, comparar Opus 5.5 con Sonnet 5.5 bajo un presupuesto declarado, y que `docker compose up` levante el sistema como promete el README.

## Fuera de alcance

- Más casos, casos de control por vector (DESIGN.md, "con más tiempo") y repeticiones con significancia estadística.
- Juez para métricas que el código puede calcular. Variantes de prompt o de esfuerzo.

## Contratos

**1. Runner** (`evals/runner.py`, `make evals VARIANT=… MAX_USD=…`; fuera de `make check`). Corre los 15 casos con `run_case` (loop real, sesión MCP fijada al cliente, `as_of` del caso) sobre un `Store` en memoria, y calcula desde la salida y las trazas:
- **Por caso:** `case_type`, acción (tipo y `txn_id`), cobertura de `expected.tools` (nombre + args clave, sin orden), recall de `policy_chunks` sobre los chunks recuperados, `no_support` y cada `must_not` verificado en código.
- **Agregado:** exactitud por métrica; **por vector**, tasa de **detectado** (señal `injection_signal`) y de **bloqueado** (validador rechazó o no hubo acción indebida), cada una con su `n`; **sobre-rechazo** (adversarial que omitió la acción legítima); costo por caso y latencia p50/p95.
- **A3:** si falla, el reporte lo marca "revisar traza antes de contar como sobre-rechazo" (variable confundida, spec 04) y no lo suma hasta que una persona lo decida.
- **Cambio aditivo en la 05b:** traza `policy_result` con los ids recuperados por `search_policies` (hoy no se persisten; sin ellos no hay recall).

**2. Presupuesto:** `MAX_USD` es obligatorio. Antes de llamar al modelo, el runner imprime la estimación (costo medio por caso de la 05b × casos × variantes + juez). Si el costo acumulado lo supera, se detiene y marca la corrida incompleta. Los precios de Sonnet 5.5 se verifican contra la página oficial al implementar, como en la 05b.

**3. Juez** (`evals/judge.py`): solo **groundedness** y **calidad de la respuesta**, con rúbrica binaria por criterio y salida estructurada. **Ciego a la variante:** recibe las respuestas de ambas variantes anónimas y en orden aleatorio (semilla registrada en la corrida); el mapeo a la variante solo lo conoce el runner.
- `make evals-label-template` escribe `evals/labels/human.json` con ~10 respuestas (enmascaradas, de la corrida más reciente) y campos vacíos. **Las etiquetas las llena una persona.** Ningún agente escribe ese archivo.
- El runner reporta el % de acuerdo juez vs humano por criterio **y por variante**, con `n`, para detectar sesgo de autopreferencia.
- **Un juez no validado no se presenta:** sin etiquetas humanas, EVALS.md reporta solo las métricas deterministas.

**4. Comparación:** las variantes `opus-5.5` y `sonnet-5.5` aparecen en una sola tabla con exactitud por métrica, bloqueo, sobre-rechazo, costo total y por caso, y latencia p50/p95. La decisión (qué modelo y por qué) la escribe una persona en EVALS.md.

**5. Salidas:** `evals/runs/<timestamp>-<variante>.json` (ignorado por git) y la tabla generada en EVALS.md, entre marcadores `<!-- runner:begin/end -->`. El resto de EVALS.md es texto humano.

**6. `docker compose up`:** el README lo promete y no existe. Un servicio `api` (API + worker en `:8001`) que sirve el build estático de la consola (decisión de la 07), con un Dockerfile multi-etapa (Node para el build, Python con uv). `ANTHROPIC_API_KEY` sale de `.env`; la base va a un volumen. El README da las URLs. Un `.dockerignore` excluye `.env`, `.env.*`, `var/` y `.local/` (enunciado confidencial); `make check` lo verifica.

## Contratos de arquitectura

- `evals` puede importar `backend`; `backend` y `mcp_server` siguen sin importar `evals` (spec 04).
- El juez no importa `backend.approval`, `backend.executor` ni `backend.store.ledger`: mide, nunca decide.

## Criterios de aceptación

1. `test_runner_metrics`: con modelo simulado sobre 3 casos (normal, adversarial bloqueado y sobre-rechazo), las métricas, los `n` y la marca de A3 coinciden con lo esperado.
2. `test_runner_stops_at_budget`: con un costo simulado que supera `MAX_USD`, se detiene y marca la corrida incompleta. Sin `MAX_USD`, no arranca.
3. `test_judge_agreement`: con etiquetas y veredictos fijos, el % de acuerdo por criterio y por variante es correcto; sin etiquetas, la sección del juez no aparece en EVALS.md. `test_judge_is_blind`: lo que recibe el juez no contiene el nombre del modelo ni de la variante, y el orden depende de la semilla.
4. `test_evals_md_table_is_generated`: solo cambia lo que está entre los marcadores.
5. `test_loop_traces_policy_results`: la traza `policy_result` existe y tiene solo ids.
6. Corrida real de las dos variantes dentro del presupuesto declarado, con la tabla en EVALS.md.
7. `docker compose up` levanta la API y la consola, verificado a mano y documentado en el README.
8. `test_dockerignore_excludes_secrets` (en `make check`): `.dockerignore` excluye `.env`, `.env.*`, `var/` y `.local/`.

## Riesgos y decisiones abiertas

1. **Repeticiones** (resuelta, se acepta la propuesta): ¿1 corrida por caso y variante, o 3 para ver la varianza? Propuesta: 1, por presupuesto. Con 15 casos, p95 ≈ máximo, y así se reporta.
2. **Modelo del juez** (resuelta, se acepta la propuesta): ¿Opus 5.5 juzgando a ambas variantes (sesgo hacia sus propias salidas) o el modelo que no se evalúa? Propuesta: Opus 5.5, con la validación humana como control del sesgo.
3. **Presupuesto máximo** (resuelta, se acepta la propuesta): la estimación de la 05b es de ~$1.45 por las dos variantes, más el juez. Propuesta: `MAX_USD=5`.
4. **Proteger `evals/labels/human.json`** (resuelta): regla `deny` de escritura en `.claude/settings.json`. No cubre redirecciones desde la shell (`>`, `tee`, un script), así que es una barrera, no una garantía. El control real es que las etiquetas entran en un commit de la persona, separado de cualquier commit del agente.
5. **`docker compose` con el modelo real** (resuelta, se acepta la propuesta): el worker llama a la API del modelo al recibir tickets. ¿Agregar un modo sin modelo (mock) para la demo sin key? Propuesta: no; sin key, el caso va a `requires_human` y la consola funciona igual.
6. **Tiempo** (resuelta): 1 h 30 min. Primer recorte: el juez completo. Sin tiempo para validarlo, EVALS.md reporta solo métricas deterministas.

## Cambios durante la implementación

<!-- Se llena al cerrar: qué cambió respecto al plan y por qué. -->

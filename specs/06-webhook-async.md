# Spec 06 — Webhook y procesamiento asíncrono

**Estado:** cerrada
**Depende de:** spec-05a, spec-05b

## Objetivo

Recibir casos por webhook de forma idempotente, procesarlos con una cola en proceso que corre `run_case`, y cerrar el gate de aprobación: solo el flujo de aprobación registra decisiones y ejecuciones, con la aprobación verificada en la misma transacción.

## Fuera de alcance

- UI (spec 07), autenticación de operadores y del emisor (spec 00), envío real de la respuesta al cliente.
- Editar la respuesta: pasa al inicio de la spec 07 como endpoint persistente (primer recorte de esta spec).
- Varios workers, colas externas, prioridades. Re-procesar un caso ya cerrado.

## Contratos

- **Webhook** `POST /webhooks/tickets`, con la cabecera `Idempotency-Key` obligatoria y un cuerpo `{ticket_id, customer_id, message}`:
  - Sin la cabecera, responde 400. Si el `customer_id` no existe, responde 422.
  - Un caso nuevo responde `202 {case_id, status: "queued"}`.
  - Un reintento con la misma clave y el mismo cuerpo devuelve el mismo `case_id` sin encolar otra vez; la misma clave con otro cuerpo responde 409. Se compara un hash del cuerpo.
  - El mensaje se persiste **enmascarado**; el prompt ya lo enmascara, así que el modelo no pierde nada. `as_of` es la hora de recepción en `America/Mexico_City`.
- **Cola** (tablas `cases` y `jobs` en SQLite):
  - `run_once()` toma un job atómicamente (de `queued` a `running`), abre la sesión MCP fijada al cliente del caso, corre `run_case` y guarda el estado final del caso: `proposal_pending`, `answered` o `requires_human`.
  - Un job `running` más viejo que un límite vuelve a `queued`. Tras 2 intentos fallidos queda `failed` y el caso pasa a `requires_human`.
  - **Sin trabajo duplicado:** `proposals` tiene `UNIQUE(case_id)`, una propuesta por caso. Un job cuyo caso ya tiene estado final o propuesta se cierra sin llamar al modelo, así que un reintento de la cola no duplica propuestas ni costo.
  - En la app, un worker en proceso llama a `run_once()` en bucle; en los tests se llama directo, con modelo falso.
- **Registro protegido de decisiones y ejecuciones** (`backend/store/ledger.py`, pendiente de la invariante 2):
  - `record_decision` y `record_execution` salen de `Store`.
  - `record_execution` inserta con `INSERT … SELECT … WHERE EXISTS (decisión 'approved')` dentro de una transacción `IMMEDIATE`. Sin aprobación, no inserta nada y lanza `NotApprovedError`, aunque alguien evada el contrato.
  - `proposals` guarda el `customer_id` del caso (pendiente de la 05a), tomado del contexto y nunca del modelo.
- **Flujo de aprobación** (`backend/approval/`; la API que usa la consola):
  - `GET /cases?status=` y `GET /cases/{id}`: mensaje enmascarado, respuesta, `reasoning_summary`, propuesta y estado.
  - `GET /cases/{id}/trace`: pasos con tokens, costo, rechazos y señales; sin bloques de thinking.
  - `POST /proposals/{id}/approve {approver}`: registra la decisión y llama al executor, que es idempotente, en una sola llamada.
  - `POST /proposals/{id}/reject {approver, reason}`.
  - **Estados terminales:** una propuesta rechazada no puede aprobarse ni una aprobada rechazarse (409). Repetir approve sobre una aprobada devuelve la misma ejecución.
  - Un `approver` vacío responde 422; más allá de eso, no se verifica (riesgo residual).

## Contratos de arquitectura

1. `protected`: a `backend.store.ledger` solo lo importan `backend.executor` y `backend.approval`. Al cerrar, cubre el contrato pendiente de la invariante 2.
2. `forbidden`: `backend.orchestrator` y el worker no importan `backend.approval`, `backend.executor` ni `backend.store.ledger`.
3. `forbidden`: `backend.approval` no importa `backend.agent`, `backend.orchestrator` ni `backend.llm`. Aprobar no toca el modelo.

## Criterios de aceptación

1. `test_webhook_is_idempotent`: la misma clave y el mismo cuerpo devuelven el mismo `case_id` y un solo job; la misma clave con otro cuerpo da 409; sin la cabecera da 400; un `customer_id` inexistente da 422.
2. `test_webhook_persists_masked_message`: ninguna fila de `cases` contiene la CLABE que traía el mensaje.
3. `test_worker_processes_queued_case`: con el modelo falso, un caso pasa de `queued` a su estado final. Un job colgado se recupera, y uno que falla dos veces termina en `requires_human`.
   `test_requeued_job_does_not_duplicate_proposal_or_model_calls`: re-procesar el job de un caso que ya tiene propuesta no llama al modelo, y la restricción `UNIQUE` impide una segunda propuesta.
4. `test_execution_requires_approval_in_same_transaction`: `record_execution` sin una decisión `approved` no inserta nada, aunque se llame directo al ledger.
5. El contrato 1, más un test de import prohibido desde `backend.orchestrator` y desde `backend.store.store`.
6. `test_approve_executes_once_and_reject_never_executes`: aprobar ejecuta una sola vez aunque se repita la llamada; rechazar nunca ejecuta.
   `test_terminal_transitions_are_forbidden[rejected→approve|approved→reject]`: cada transición prohibida responde 409 y no cambia nada.
   `test_empty_approver_is_rejected`: un `approver` vacío responde 422.
7. `test_case_api_exposes_no_sensitive_data`: las respuestas de `/cases` y `/trace` no tienen hallazgos de `find_sensitive` ni bloques de thinking.

## Riesgos y decisiones

Resueltas:
1. **`Idempotency-Key` obligatoria;** sin ella, 400.
2. **Sin HMAC del emisor**, como riesgo residual en DESIGN.md. El impacto se limita a ruido y costo de modelo: un caso falso solo produce una propuesta que pasa por aprobación humana.
3. **`approver` sin verificar**, como riesgo residual; como mínimo, se rechaza vacío.
4. **Aprobar y ejecutar en una llamada**, con estados terminales y un test por cada transición prohibida.
5. **Solo el mensaje enmascarado** queda en reposo: una decisión de minimización de datos, registrada en DESIGN.md.
6. **Tiempo: 70 min.** El primer recorte es el endpoint de edición de la respuesta, que pasa al inicio de la spec 07 como endpoint persistente.

## Cambios durante la implementación

- `record_decision` y `record_execution` salieron de `Store` a `backend/store/ledger.py`. Los tests del gate solo cambiaron la forma de llamar al código, con el diff revisado por el usuario y el mismo número de aserciones (12 y 17).
- `conclude` traza `answer` (case_type y customer_reply) para la vista de la consola, y pasa el `customer_id` del contexto a la propuesta.
- security-reviewer: bloqueó una vez.
  - La conexión SQLite compartida entre el pool de hilos de la API y el worker mezclaba transacciones: 267 de 300 rondas concurrentes con excepciones, y 25 donde la API respondía "rechazada" con otra decisión registrada. Se resolvió con un `RLock` que serializa el `Store` y las secuencias del ledger y la aprobación, más un test de concurrencia.
  - El ledger se podía alterar con SQL crudo: se agregaron triggers solo de inserción con `recursive_triggers` y una guarda de texto ampliada.
  - Tras los arreglos dio OK, con la prueba de 300 rondas limpia.
- A 10x, el `RLock` no basta: con varios procesos, la serialización debe bajar a la base de datos (DESIGN.md).
- Hallazgos menores resueltos: un caso con propuesta que quedaba en `queued`; un job colgado que se reprocesaba sin límite; tests que no ejercitaban el filtro de `prompt` ni el salto de casos terminados.
- Correcciones a tests propios: cuerpos de petición por endpoint en las transiciones terminales; filas reales en el test de solo inserción.
- Opcional hecho: guarda de texto de escrituras al ledger fuera de `ledger.py`, incluido `DROP TRIGGER`.
- La edición de la respuesta pasa al inicio de la spec 07, como endpoint persistente.

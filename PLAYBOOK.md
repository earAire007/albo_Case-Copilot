# PLAYBOOK — Replicar este patrón en tu equipo

Para equipos de albo que quieren un agente que investigue casos y proponga qué hacer, sin ser expertos en IA. La idea central: **el modelo propone, una persona decide y el código ejecuta.** Todo lo demás protege esa frase.

## Qué pueden reutilizar tal cual

- **`AGENTS.md`**: las reglas para cualquier asistente de código que trabaje en el repo (Claude Code, Cursor, Copilot). Cambien el contexto en una línea y la estructura; las reglas no negociables sirven igual.
- **La plantilla de spec** (`specs/_template.md`) y su ciclo: una página por etapa, con criterios de aceptación que se comprueban con un test. Primero la spec, luego los tests, luego el código.
- **`/check-docs`** (`scripts/check_docs.py` y `.claude/commands/check-docs.md`): comprueba que cada garantía de seguridad escrita en el diseño tenga un test que exista de verdad.
- **El revisor de seguridad** (`.claude/agents/security-reviewer.md`): un agente que revisa cada cambio contra las garantías antes del commit. Solo lee; no edita.
- **El runner de evals con candado de etiquetas** (`evals/`): corre los casos con el modelo real, calcula las métricas en código y se niega a usar el juez si las etiquetas humanas no están guardadas en git, limpias y completas.

## Qué tienen que adaptar

- **El dominio**: los datos de ejemplo (`data/`), los tipos de caso y las acciones que el agente puede proponer. Las acciones son una lista cerrada, y ninguna mueve dinero.
- **Las tools del MCP** (`mcp_server/`): las consultas que el agente puede hacer a sus sistemas. Solo lectura, y siempre fijadas al cliente del caso.
- **Las políticas**: los documentos que el agente cita para justificar su respuesta.
- **Los casos de eval**: 15 casos reales de su operación, incluidos ataques, etiquetados por su gente **antes** de construir el agente.
- **Los datos sensibles**: aquí son CLABE, tarjeta, RFC y CURP; agreguen los suyos al detector.

## Reglas que no se negocian

### Seguridad

- **Ninguna tool mueve dinero, y toda acción pasa por una persona.** Una política envenenada le pidió al agente un reembolso: el modelo no la siguió, y aunque la hubiera seguido, no existía con qué hacerlo.
- **El cliente lo fija el sistema, nunca el modelo.** En el caso de otra cuenta, pedir datos ajenos devuelve el mismo error que un id inexistente: no hay manera de preguntar.
- **Los datos sensibles se enmascaran antes de llegar al modelo, a los logs o a las trazas.** El sensor de los tests atrapó una CLABE completa en un error que había escrito el propio asistente de código.
- **Lo que escribe un cliente, una política o una tool es dato, no instrucción.** Sembramos instrucciones falsas en un concepto de SPEI y en una política; las dos llegaron marcadas como no confiables.
- **Revisión de seguridad antes de cada cambio en la frontera.** El revisor encontró que el nombre del caso de prueba llegaba al modelo: sabía que lo estaban atacando, y nuestras métricas de bloqueo no valían.

### Evals

- **Las etiquetas se escriben antes que el agente.** Si se escriben después, sin querer se escribe lo que el agente ya hace bien.
- **Las etiquetas humanas las pone una persona y se guardan en git antes de correr el juez.** En la primera ronda se guardaron después y esa ronda ya no se puede verificar como ciega; desde entonces, el candado lo exige.
- **Un juez automático no se presenta sin validarlo contra personas.** En la segunda ronda, cuatro de cinco desacuerdos eran culpa de la evidencia incompleta que le dimos al juez; el quinto fue un error real que nadie más vio.
- **Lean los casos uno por uno, no solo el porcentaje.** Así encontramos dos errores en la propia medición.
- **Verifiquen de punta a punta desde una copia limpia del repo.** Con más de 400 tests en verde, el servicio no arrancaba con el archivo de ejemplo, y sin key los casos fallaban sin decir por qué.

### Costo

- **Cada corrida con el modelo real declara su presupuesto y se detiene al superarlo** (`MAX_USD`). La comparación de dos modelos estaba estimada en ~$1.45; el tope fue $5.
- **Ninguna llamada al modelo real sin permiso, ni para "probar rápido".** Una prueba de un token "sin key" salió con una credencial que nadie esperaba.
- **Fallar cerrado cuesta trabajo humano: mídanlo.** Los validadores mandaron a revisión 2 de 30 respuestas correctas; no se corrigió, pero ahora se sabe cuánto cuesta.

## ¿Mi agente está listo para producción?

- [ ] Ninguna tool escribe, mueve dinero ni acepta el id del cliente como argumento.
- [ ] Toda acción queda pendiente hasta que una persona la aprueba, y la aprobación queda registrada.
- [ ] Los datos sensibles salen enmascarados en el modelo, los logs, las trazas y la consola, y hay un test que falla si no.
- [ ] Cada garantía de seguridad tiene un test, y `make check` (con `/check-docs`) pasa.
- [ ] El revisor de seguridad revisó los cambios en la frontera.
- [ ] Hay casos de eval etiquetados por personas, con ataques por cada vía de entrada, y una corrida real dentro del presupuesto.
- [ ] Si usan un juez automático, está validado contra etiquetas humanas guardadas antes de correrlo.
- [ ] Sin key o con el proveedor caído, los casos van a una persona con un motivo legible, y el arranque lo avisa.
- [ ] Alguien levantó el sistema desde una copia limpia con `docker compose up` e hizo el recorrido completo.
- [ ] Saben qué miran en producción: casos derivados a personas por motivo, rechazos por validador, costo y latencia por caso.

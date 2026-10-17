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

**Qué fue.** En la spec 02, el agente endureció el servidor MCP para que cualquier excepción inesperada saliera como un `Internal server error` genérico. Para no perder el diagnóstico, agregó `_logger.exception(...)` en un logger propio (`mcp_server.server`). Ese logger no tenía el filtro de enmascarado que sí tenían los del SDK, y el traceback llevaba la CLABE del cliente en claro. Era una fuga de datos sensibles a logs, justo lo que prohíbe la invariante 4.

**Cómo me di cuenta.** No me di cuenta yo: se dio cuenta el sistema que construimos para eso. El sensor de fugas de la spec 01b (un plugin de pytest que revisa logs, stdout, stderr y excepciones de cada test) hizo fallar el test en el teardown, antes del commit. Ninguna aserción buscaba ese caso; falló un sensor genérico. La corrección fue instalar el filtro también en ese logger (commit `0790ba5`).

**Qué me deja.** Es la prueba concreta de que la spec 01b valía lo que costó: los sensores computacionales atrapan errores que nadie pensó en probar, incluidos los del agente que escribe el código.

## Qué NO delegué a ciegas

<!-- Guardrails, gate de aprobación, evals -->

---

## Bitácora (en caliente)

<!-- Formato: fecha · commit · qué pasó (2 líneas). De aquí salen las secciones de arriba. -->

- 2026-10-16 · inicial · Planeación con agente: definimos SDD ligero con 7 specs y pusimos evals antes del harness.
- 2026-10-16 · 943b634 · Claude Code propuso agregar injection en el concepto de un SPEI (vector indirecto vía resultado de tool, no pedido por el reto). La evalué, la acoté a un escenario y un caso, y detecté que la invariante 5 no cubría resultados de tools; la actualicé.
- 2026-10-16 · 0205916 · Mi instrucción de tests para la spec 01 tenía una inconsistencia: pedía verificar "la CLABE destino del escenario de injection", pero en la spec ese escenario no tenía CLABE destino. El agente la detectó porque contrastó la instrucción con la spec en lugar de inventar un escenario que encajara, y me preguntó. Ajustamos la spec antes del código: el "spec como contrato" funciona en ambas direcciones.
- 2026-10-16 · f08128c · Revisé el enfoque contra el concepto de harness engineering: teníamos buen contexto (AGENTS.md, specs) pero ningún sensor computacional; las reglas no negociables solo estaban escritas. Agregué la spec 01b antes de la 02 para que la frontera de seguridad nazca con sensores activos.
- 2026-10-16 · 9e49c19 · Al implementar la 01b, el agente detectó antes de escribir código que el AC5 tal como estaba escrito creaba recursión infinita (test del hook Stop → make test → test → …) y que pytester en el mismo proceso haría que el fixture externo capturara los logs del test interno. Propuso ajustar la spec (comando inyectable por env, plugin + subprocess) en vez de forzar los tests.
- 2026-10-16 · 6697845 · Primera corrida de /check-docs: el script determinista dio OK, pero la revisión semántica encontró que 5 de 6 invariantes no tenían test ni marca de pendiente y que 3 tests existentes cubrían solo parte de su invariante (API mock, no MCP; logs, no modelo ni trazas). Un sensor en verde no prueba cobertura: agregué reglas a check_docs.py para que ese hueco sea un ERROR determinista.
- 2026-10-16 · spec-01b · Segunda revisión contra harness engineering antes de cerrar la 01b: los sensores solo corren dentro de Claude Code (hooks en .claude/settings.json), pero AGENTS.md promete que el setup no depende de una herramienta. Agregué `make check` (lint + test + check-docs) como regla antes de cada commit; pre-commit y CI quedan fuera por tiempo y se documentan como riesgo residual en DESIGN.md.
- 2026-10-16 · 0790ba5 · security-reviewer verificó los tests con mutaciones (desactivar el enmascarado rompe 22 tests). De sus hallazgos menores, uno proponía que el filtro de logs, si fallaba, dejara el registro sin cambios: fallar abierto en un sensor de datos sensibles. Lo cambié a fallar cerrado (redactar el mensaje completo).
- 2026-10-16 · 0790ba5 · El sensor de fugas de la spec 01b atrapó una fuga real en código que escribió el agente, antes del commit: al convertir excepciones genéricas en "Internal server error", agregó `_logger.exception(...)` en un logger propio (`mcp_server.server`) sin el filtro de enmascarado, y el traceback llevaba la CLABE. El test falló en el teardown por el sensor, no por una aserción escrita para ese caso. Se corrigió instalando el filtro también en ese logger. No me di cuenta yo: se dio cuenta el sistema que construimos para eso. Es la prueba concreta de que la spec 01b valía lo que costó.
- 2026-10-16 · 30aa818 · El chequeo de cordura del agente mostró que el umbral calibrado en la spec 03 deja pasar chunks irrelevantes con consultas reales, justo lo que la spec había marcado como optimista: una medición que confirmó un riesgo documentado, en lugar de que se quedara en teoría.
- 2026-10-16 · 0d49665 · Hallazgo que hice leyendo el plan contra los contratos, no un sensor: el agente propuso poner `run_turn` en `backend/agent` persistiendo con `backend/executor/store.py`, una estructura razonable que habría obligado a romper su propio contrato de arquitectura (el agente no importa el executor). Lo reorganicé en agent puro, store neutral, orchestrator y executor, con un contrato por frontera. Material para "qué NO delegué a ciegas".
- 2026-10-16 · a198a6b · security-reviewer bloqueó la 05a con evasiones que los tests no cubrían: CC antepuesto a una CLABE pasaba como clave de rastreo, y los separadores evadían el validador de dígitos. La excepción pasó de eximir el formato a eximir solo claves devueltas por las tools del caso. Tercera vez que un revisor adversarial separado encuentra lo que los tests del autor no: los validadores deterministas valen lo que el adversario que los prueba.
- 2026-10-16 · 37b4e2c · Segunda vez que /check-docs encuentra una inconsistencia que una revisión humana dejó pasar en un cierre: tras cerrar la 05a, la invariante 2 figuraba como completa aunque el gate se podía saltar por la API del `Store`, y el detector de injection que prometía la spec 03 no estaba asignado a ninguna spec. Evidencia de que la recolección de basura no es un adorno.

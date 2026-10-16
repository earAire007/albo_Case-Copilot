---
description: Verifica coherencia entre spec 00, DESIGN.md, specs/README.md y los tests
---

Revisa la coherencia de la documentación del repo. **No edites nada**: reporta y propone.

1. Corre `make check-docs`. Si falla, lista cada `ERROR` y propón la corrección concreta (qué archivo, qué línea, qué texto).
2. Revisión semántica, que el script no cubre. Lee `specs/00-fundamentos.md` (sección "Modelo de defensa") y la tabla de invariantes de `DESIGN.md`:
   - ¿Coinciden número, nombre y alcance de cada invariante? Señala cualquier diferencia de alcance (p. ej., la spec 00 cubre "resultados de tools" y DESIGN.md no lo menciona).
   - Para cada test nombrado que exista, lee su cuerpo: ¿verifica lo que afirma la invariante o algo más débil?
   - ¿Hay invariantes sin test ni marca de pendiente?
3. Responde con dos secciones: **Determinista** (salida del script) y **Semántico** (hallazgos con archivo:línea). Si todo está bien, dilo en una línea.

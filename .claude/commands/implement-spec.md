---
description: Implementa una spec de specs/ siguiendo el flujo del repo
argument-hint: <id de spec, ej. 02>
---

Vas a implementar la spec $ARGUMENTS.

1. Lee `AGENTS.md`, `specs/README.md` y `specs/$ARGUMENTS-*.md`.
2. Si algo de la spec es ambiguo o contradice el código existente, detente y propón el cambio a la spec.
3. Presenta un plan de máximo 8 pasos que mapee cada criterio de aceptación a un test. Espera mi OK.
4. Escribe primero los tests de los criterios críticos (gate, enmascarado, idempotencia, validación). Córrelos y confirma que fallan.
5. Implementa hasta que pasen. No modifiques los tests para que pasen.
6. Al terminar: corre `make test`, resume qué cambió respecto a la spec y propón el texto para la sección "Cambios durante la implementación".

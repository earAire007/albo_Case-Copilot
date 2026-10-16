# DESIGN

<!-- Documento vivo: cada spec agrega o actualiza su sección al cerrarse. -->

## Arquitectura del harness

<!-- spec 05 -->

## Modelo de defensa

Invariantes definidas en `specs/00-fundamentos.md`. Cada una con el test que la verifica:

| # | Invariante | Test |
|---|------------|------|
| 1 | Sin capacidad de mover dinero | <!-- --> |
| 2 | Planner/executor separados, gate humano en código | <!-- --> |
| 3 | Scoping de `customer_id` por capacidad | <!-- --> |
| 4 | Enmascarado de datos sensibles en la frontera | <!-- --> |
| 5 | Contenido no confiable delimitado | <!-- --> |
| 6 | Groundedness verificada en código | <!-- --> |

### Riesgo residual y cómo se detecta en producción

<!-- -->

## Contexto y costos

<!-- spec 02 y 05 -->

## Manejo de fallas del proveedor

<!-- spec 05 -->

## Observabilidad y alertas

<!-- spec 05 -->

## Trade-offs y decisiones

<!-- -->

## Qué recorté y por qué

<!-- -->

## Qué se rompe a 10x casos o con diez agentes compartiendo herramientas

<!-- -->

## Qué haría con más tiempo

<!-- -->

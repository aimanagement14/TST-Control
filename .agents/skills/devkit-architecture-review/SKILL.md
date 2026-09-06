---
name: devkit-architecture-review
description: Revisa cambios estructurales sobre la CLI, servicios o plantillas del kit.
---

# devkit-architecture-review

Usar **antes** de fusionar un cambio que modifique la arquitectura del kit:
nuevos comandos, servicios, diagnósticos, descriptores de plantillas o skills.

## Cuándo usarla

- Se añade un comando o se cambia la firma pública de uno existente.
- Se introduce un nuevo servicio o se divide uno.
- Se añade una nueva plantilla o campo en `template.config.json`.
- Se introduce una nueva regla de diagnóstico.

## Procedimiento

1. Comprobar que el cambio respeta la separación
   `commands → services → diagnostics` descrita en
   `docs/reference/architecture.md`.
2. Validar que los servicios siguen siendo testeables y no imprimen en consola.
3. Validar que `DevkitError` se usa para errores tipados.
4. Validar que los descriptores (`template.config.json`,
   `schemas/config.schema.json`) se actualizan a la vez que el código.
5. Comprobar que ningún cambio rompe compatibilidad hacia atrás. Si la rompe,
   documentarlo en `CHANGELOG.md`.

## Entregable

- Lista de capas afectadas y justificación.
- Impacto en la API pública (sí/no) y migración si aplica.
- Riesgos conocidos.
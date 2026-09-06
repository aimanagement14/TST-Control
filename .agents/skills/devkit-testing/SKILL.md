---
name: devkit-testing
description: Decide qué pruebas ejecutar antes de cerrar un cambio en el kit.
---

# devkit-testing

Usar **siempre** antes de declarar un cambio como completo. No cierra una tarea
si las pruebas no pasan.

## Cuándo usarla

- Cualquier cambio en `src/` (CLI, servicios, diagnósticos).
- Cualquier cambio en `templates/*/template.config.json`.
- Cualquier cambio en skills o en `AGENTS.md` que afecte al flujo de la CLI.

## Procedimiento

1. Identificar el scope del cambio (CLI, plantilla, skill, documentación).
2. Seleccionar las comprobaciones mínimas:

   | Scope | Comprobaciones |
   | --- | --- |
   | CLI TypeScript | `npm run typecheck`, `npm run build`, `npm test` |
   | Plantilla TS | `npm run lint`, `npm run typecheck`, `npm test` |
   | Plantilla Python | `pytest -q`, `ruff check src tests`, `ruff format --check src tests`, `mypy src/autoedit` |
   | Skills | `devkit skills validate` |
3. Ejecutar las comprobaciones en el directorio correcto.
4. Si alguna falla, NO marcar el cambio como completo.
5. Si el cambio introduce un nuevo comportamiento, añadir al menos un test que
   lo cubra.

## Entregable

- Lista de comandos ejecutados y su resultado.
- Tests añadidos o actualizados.
- Confirmación de que el cambio no rompe proyectos existentes generados con
  `devkit new`.
---
name: devkit-project-intake
description: Define alcance, criterios de aceptación y plan mínimo antes de modificar código del kit.
---

# devkit-project-intake

Usar **antes** de proponer cambios no triviales en Developer-Kit. Es la fase de
intake: no tocar archivos hasta tener un plan validado.

## Cuándo usarla

- Aparece una nueva funcionalidad que afecta a la CLI, plantillas o skills.
- Hay un bug cuyo origen no es evidente.
- Hay que refactorizar un módulo existente.

## Procedimiento

1. Leer `AGENTS.md` raíz, `docs/reference/architecture.md` y el descriptor
   de la plantilla o servicio afectado.
2. Identificar archivos que serán modificados y los que NO se deben tocar.
3. Redactar criterios de aceptación verificables (uno por bullet):
   - comportamiento observable;
   - comando o test que lo verifica.
4. Listar los `SKILL.md` del kit que aplicarán después (`devkit-testing`,
   `devkit-code-review`, etc.).
5. Definir un plan por pasos pequeños. Cada paso debe poder revertirse de forma
   aislada.

## Entregable

- Lista de archivos a tocar.
- Lista de archivos a NO tocar.
- Criterios de aceptación.
- Plan paso a paso.
- Skills que se aplicarán durante la implementación.

## Restricciones

- No escribir código todavía.
- No modificar `CHANGELOG.md`.
- No añadir dependencias sin aprobación explícita.
---
name: devkit-code-review
description: Revisa un Pull Request o parche sin ejecutar el código.
---

# devkit-code-review

Usar para auditar un cambio antes de fusionarlo. Solo lectura: no modificar
archivos durante la revisión.

## Cuándo usarla

- Revisar un Pull Request.
- Auditar un parche propuesto por otro agente.
- Validar un commit antes de mergearlo.

## Procedimiento

1. Leer la descripción del cambio y mapear archivos tocados contra el plan
   definido en `devkit-project-intake`.
2. Buscar, en este orden:
   1. Errores de tipo (`any`, casts inseguros, `as unknown as`).
   2. Cambios que rompen la separación `commands → services → diagnostics`.
   3. Falta de tests o tests que no cubren el cambio.
   4. Errores tipados con `throw new Error(...)` en lugar de `DevkitError`.
   5. Dependencias añadidas sin justificación.
   6. Secretos, URLs internas o PII en el diff.
3. Verificar que la documentación correspondiente está actualizada
   (`docs/commands.md`, `checklists/`, `AGENTS.md` raíz).

## Entregable

- Lista priorizada de issues (severidad alta → baja).
- Sugerencias opcionales separadas.
- Veredicto: `approve`, `request changes` o `comment`.
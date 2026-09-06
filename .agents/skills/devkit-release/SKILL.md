---
name: devkit-release
description: Coordina bumps de versión y entradas de CHANGELOG.
---

# devkit-release

Usar **solo** cuando un cambio merece un bump de versión y entrada
en `CHANGELOG.md`. Developer-Kit no se publica en el registry de npm,
así que "release" aquí significa "corte de versión local".

## Cuándo usarla

- Se va a bumpear la versión en `package.json`.
- Se va a modificar `CHANGELOG.md` con una entrada nueva.
- Se va a etiquetar un commit con `git tag v<versión>`.

## Procedimiento

1. Confirmar que `main` está en verde: `npm run typecheck`,
   `npm run build`, `npm test` y `npm run validate` (incluye
   `devkit skills validate`).
2. Decidir el bump (`patch`, `minor`, `major`) siguiendo SemVer.
3. Actualizar `package.json#version` y `CHANGELOG.md` en el mismo
   commit.
4. Validar que los archivos listados en la sección **Changed**
   siguen existiendo y compilan.
5. Crear el tag con el prefijo `v` (por ejemplo `v0.3.0`).

## Restricciones

- No bumpear sin haber ejecutado `devkit doctor` en un entorno limpio.
- No saltar la entrada en `CHANGELOG.md`.
- No fusionar cambios de versión directamente sobre `main` sin
  Pull Request.

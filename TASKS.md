# Tasks

Backlog vivo. Las tareas cerradas se archivan al `CHANGELOG.md` al
publicarse una versión.

## Pendientes

- [ ] Ninguna abierta en este momento.

## Cerradas (vista resumida)

### Auditoría 2026-08-29

- [x] Inventariar proyecto (estructura, dependencias, código, docs, tests).
- [x] Ejecutar `test_core.py` y `verify_fosiles.py` para detectar errores.
- [x] Auditar código (parsers, QC, rutas, persistencia, prompts).
- [x] Consultar context7 para validar patrones actuales de Flask 3 y Jinja2.
- [x] Corregir bug: QC nunca marca `ready` con warnings.
- [x] Corregir docs/templates que decían `07_paquete_completo.json`.
- [x] `verify_fosiles.py`: crear proyecto si no existe.
- [x] `test_core.py`: `gc.collect()` entre tests para limpiar SQLite en Windows.
- [x] Limpiar `_stage_context` con código duplicado.
- [x] Mover `import urllib.request` al top.
- [x] Renderizar `profile['platforms']` como lista en metadata prompt.
- [x] Corregir margin-top del footer en `style.css`.
- [x] Rellenar `docs/ARCHITECTURE.md` y `docs/DECISIONS.md`.
- [x] Actualizar `CHANGELOG.md` y `README.md` con la nueva estructura.
- [x] Re-validar tests + verify_fosiles.py tras los cambios.

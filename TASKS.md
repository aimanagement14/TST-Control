# Tasks

Backlog vivo. Las tareas cerradas se archivan al `CHANGELOG.md` al
publicarse una versión.

## Pendientes

- [ ] Generar las escenas del guion corto (1 min) en proyectos que ya
  tienen escenas solo para el guion largo. La etapa Escenas ahora
  exige ambos sets antes de marcarse como lista.

## Cerradas (vista resumida)

### Reducción de pipeline 2026-08-29

- [x] Eliminar etapa 06 «Prompts visuales» (ruta, plantilla, builder,
  export, QC, config.json).
- [x] Renumerar etapas: 07→06 (Metadata) y 08→07 (QC).
- [x] Renumerar export: `05_metadata/`, `06_prompts_usados.md`,
  `07_paquete_completo.json`.
- [x] Renombrar ruta `/projects/<id>/prompts/backfill` a
  `/projects/<id>/stage-prompts/backfill` (no tiene que ver con la etapa
  visual).
- [x] Escenas: status LISTO exige mínimo de escenas para AMBOS guiones.
- [x] Escenas: tab activo calculado con `namespace()` (Jinja2) para
  que `script_id` de la URL se respete siempre; estilo más claro del
  tab activo (borde inferior ámbar).
- [x] Actualizar `README.md`, `docs/ARCHITECTURE.md`,
  `docs/DECISIONS.md`, `CHANGELOG.md` con la nueva estructura.
- [x] `verify_fosiles.py`: saltarse etapa 06 (ya no existe) y validar
  el nuevo `07_paquete_completo.json`.
- [x] `test_core.py`: quitar inserciones de `prompts` y aserción sobre
  `08_paquete_completo.json`.
- [x] Re-validar `test_core.py` + `verify_fosiles.py` tras los cambios.

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

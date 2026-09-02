# Tasks

Backlog vivo. Las tareas cerradas se archivan al `CHANGELOG.md` al
publicarse una versión.

## Pendientes

### Sprint auditoría 2026-09 (Phase 0 — Quick wins)

- [x] T0.1 — `secret_key` desde variable de entorno
  (`FLASK_SECRET_KEY`), con fallback a `config.json` solo para dev.
- [x] T0.2 — Corregir "7 etapas" en `PRODUCT.md` y `README.md` (ahora
  8 etapas: research → concept → scripts → scenes → metadata →
  thumbnails → qc → export).
- [x] T0.3 — Añadir `static/uploads/` a `.gitignore`.
- [x] T0.4 — Logging estructurado (`logging.basicConfig` + logger
  `tst`) en arranque y rutas; nivel configurable con `TST_LOG_LEVEL`.

### Sprint auditoría 2026-09 (Phase 1 — Dependencias y CI)

- [x] T1.1 — Lockfile reproducible: `requirements.in` (specs) +
  `requirements.lock` (versions pinned de transitivas) +
  `requirements.txt` (copia del lock para `pip install` directo en
  CI y dev).
- [x] T1.2 — Workflow de CI en `.github/workflows/ci.yml`: corre
  `test_core.py` y `verify_project.py` en Python 3.13 sobre
  `push` y `pull_request` a `main`. Badge en `README.md`.

- [ ] Generar las escenas del guion corto (1 min) en proyectos que ya
  tienen escenas solo para el guion largo. La etapa Escenas ahora
  exige ambos sets antes de marcarse como lista.
- [ ] Sustituir importmap de esm.sh por bundles locales en
  `static/vendor/` si se requiere soporte offline. Evaluar primero
  con `chrome://network` cuánto pesa cada recarga en una red lenta.
- [ ] Añadir tests E2E del runner vía `app.test_client()` que
  verifiquen cambio de estado `idle → running → ok` en
  `node_executions` para los 9 nodos fijos.

### Editor de grafo 2026-09-01

- [x] Migrar `stage_prompts` por proyecto a `profile_prompts` por
  perfil; migración idempotente en `init_db()` con backup
  `workflow.db.bak` y flag en `_schema_migrations`.
- [x] `resolve_stage_prompt(profile_id, stage)` como única vía de
  lectura; fallback a `config.json`. Refactor de los seis handlers
  para usarla; eliminada la acción POST `save_prompt` y los helpers
  `get_saved_prompt` / `save_stage_prompt` /
  `list_saved_prompts` / `_ensure_stage_prompt` /
  `backfill_stage_prompts`.
- [x] Tablas nuevas `profile_graph_nodes` (con `is_fixed`, posiciones,
  `inputs_json`) y `node_executions` (estado, output, duración).
- [x] Siete rutas nuevas: `/profiles/<id>/graph` (GET),
  `/profiles/<id>/graph/save-node` (POST),
  `/profiles/<id>/graph/delete-node` (POST),
  `/profiles/<id>/graph/layout` (POST),
  `/projects/<id>/run` (GET),
  `/projects/<id>/run/execute` (POST),
  `/projects/<id>/run/reset-node` (POST).
- [x] Ejecutor unificado `execute_graph_node()` que despacha a los
  builders/parsers existentes para los nueve nodos fijos y hace
  `call_llm` directo para los custom, interpolando `{{ inputs.x }}`.
- [x] `templates/profile_graph.html` y `templates/project_run.html`
  con layout split, importmap a `@xyflow/react@12.11.6` desde
  `esm.sh`, panel lateral de edición y barra de estado por nodo.
- [x] `static/graph.js` como módulo ESM con el componente React
  Flow, nodos custom (add/remove), persistencia de posiciones con
  debounce 600 ms y mocks `TODO` para los endpoints hasta la
  integración final.
- [x] `templates/project.html` reemplaza el panel «Prompts
  guardados» por un enlace al editor de grafo del perfil.
- [x] `static/style.css` con estilos del chrome del grafo y los
  estados idle/running/ok/error (variables CSS del tema).
- [x] Tests: `resolve_stage_prompt` con fallback, UPSERT de
  `save_profile_prompt`, copia de `stage_prompts` a
  `profile_prompts`, `get_or_create_fixed_graph_nodes`, save+delete
  de nodo custom, `update_graph_layout`, y `execute_graph_node`
  para un fijo y un custom en modo manual.
- [x] Documentación: `docs/ARCHITECTURE.md` (sección Editor de
  grafo), `docs/DECISIONS.md` (ADRs 2026-09-01), `TASKS.md`,
  `CHANGELOG.md` y `README.md`.

### Etapa Miniaturas 2026-08-29

- [x] Añadir plantillas `thumbnail_long` y `thumbnail_short` en
  `config.json` (heredan keywords de estilo de `scenes`).
- [x] Tabla `thumbnail_records` con `UNIQUE(project_id, script_type)`.
- [x] `build_thumbnail_prompt`, `parse_thumbnail`, builder entries y
  ramas en `_stage_context` / `_ensure_stage_prompt`.
- [x] Ruta `thumbnails(project_id)` y plantilla `thumbnails.html`
  con dos paneles estilo `metadata`.
- [x] Insertar etapa `thumbnails` (07) en `PIPELINE_STAGES`,
  `PAGE_ORDER`, `PAGE_LABELS`, `STATUS_LABELS`. Renumerar QC a 08.
- [x] `project_stage_status`: thumbnails done solo con ambos scripts.
- [x] Export: `06_thumbnails/`, renumerar `06_prompts_usados.md` → `07`
  y `07_paquete_completo.json` → `08`. Bundle JSON incluye `thumbnails`.
- [x] Tests: `test_parse_thumbnail` + asserts en `verify_fosiles.py`.
- [x] Documentación: README, CHANGELOG, ARCHITECTURE, DECISIONS,
  templates (`project.html`, `qc.html`, `export.html`).

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

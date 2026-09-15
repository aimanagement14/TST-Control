# Tasks

Backlog vivo. Las tareas cerradas se archivan al `CHANGELOG.md` al
publicarse una versión.

## Pendientes

### Sprint auditoría 2026-09-05 (continuación — monolito + tooling)

- [x] **R1** Extraer `sync_project_folder`, `safe_project_dir` y
  `delete_project_folder` a `services/sync.py`. Re-exportar desde
  `app.py` para preservar `app.safe_project_dir` y
  `app.sync_project_folder` (usados por `test_core.py`).
- [x] **R2** Extraer `/profiles` y `/settings` a
  `blueprints/profiles.py` (`profiles_bp`) y `blueprints/settings.py`
  (`settings_bp`). `strict_slashes=False` para no romper los tests.
  Renombrar endpoints a `profiles.view` y `settings.view`.
  **Cumplido en T2.2; `/settings` revertido en v2.0.0** al
  retirar `blueprints/settings.py`, `templates/settings.html` y la
  pestaña "Configuración" del nav (CHANGELOG 2.0.0). Solo sobrevive
  `profiles_bp` con `profiles.view`.
- [x] **H1** Commitear `projects/Todo_sobre_La_Piedra_Rúnica_13/`
  (nuevo) + etapas 01–06 de `projects/Todo_sobre_la_Antártida_12/`
  que estaban untracked.
- [x] **H2** Alinear Python canónico: AGENTS.md «3.14» → «3.13»,
  README.md con nota «Python: 3.13», `.python-version` nuevo.
- [x] **H3** Archivar `docs/SPRINT-2026-09-audit.md` →
  `docs/archive/` con header de «Archivado» (paths legacy).
- [x] **H4** Eliminar `requirements.lock` (duplicado literal de
  `requirements.txt`).
- [x] **H5** `pyproject.toml` mínimo con `requires-python` y config
  opcional de `ruff`/`mypy`.
- [x] **H6** `scripts/validate.py` (equivalente `npm run validate`):
  pyflakes/tests/e2e obligatorios; ruff/mypy informativos.
- [x] **H7** Añadir cobertura E2E de `scenes_short` al
  `verify_project.py`. Antes solo se ejercitaba el guion largo.

### Pendiente para futuro sprint

- [ ] Resolver el **1 hallazgo actual de ruff** (F841 en
  `test_core.py:2254`) — bloquea `ruff check` que ya corre con
  `required=True` en `scripts/validate.py:121`. Decidir también si
  subir `mypy` de `required=False` a `required=True`; hoy reporta
  6 avisos «annotation-unchecked» como informativos.
- [ ] Evaluar extracción de las 8 rutas por etapa
  (`research`/`concept`/`scripts`/`scenes`/`metadata`/`thumbnails`/
  `qc`/`export`) a blueprints dedicados. La bloqueante es
  `fetch_project_or_404` y los builders de prompts, que viven en
  `app.py` y se reusan en varios handlers.

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

### Sprint auditoría 2026-09 (Phase 2 — Extracción del monolito, PoC)

- [x] T2.1 — Carpeta `services/`: parsers puros, `call_llm` y QC
  (`services/parsers.py`, `services/llm.py`, `services/qc.py`).
  `app.py` re-exporta los símbolos para preservar la API.
- [x] T2.2 — Blueprints `blueprints/graph.py` (`graph_bp`) y
  `blueprints/runner.py` (`runner_bp`) con las 4 + 3 rutas
  aisladas. Local imports en handlers para romper ciclos.
  **Purgado en v2.1.0 (ADR 2026-09-11)**: ambos blueprints fuera
  de scope, código muerto eliminado.
- [x] T2.3 — ADR-010 (`docs/DECISIONS.md`) documenta la PoC
  con contexto, decisión, consecuencias y reversibilidad
  explícita. `docs/ARCHITECTURE.md` actualizado con el diagrama
  y la tabla de módulos.

### Sprint auditoría 2026-09 (Phase 3 — Robustez)

- [x] T3.1 — Logging en `except Exception:` silenciosos. Cubre
  ~20 casos en `app.py` (rollback teardown, json.loads en parser
  best-effort, JSON.parse de platforms, etc.) y los 7 de
  `services/parsers.py` / `services/llm.py`. Criterio:
  `log.exception` para críticos de mutación, `log.warning` para
  recuperables, `log.debug` para silenciosos legítimos con
  comentario. Las referencias a `node_executions` se retiraron
  con la purga del runner en v2.1.0.
- [x] T3.2 — ~~`static/graph.js` dividido en 4 módulos ESM bajo
  `static/graph/`~~. **Purgado en v2.1.0** al retirarse el editor
  de grafo y el runner; el árbol vuelve a tener un único
  `app.js` + `copy-fields.js` sin dependencias externas.
- [x] T3.3 — Muestra oficial `Todo_sobre_los_Fosiles_1/` movida
  a `examples/` con `git mv` (preserva historial). `projects/`
  queda con `.gitkeep` que explica que su contenido lo genera la
  app en runtime. `app.py` ya usaba `PROJECTS_DIR`, sin paths
  hardcodeados.

- [x] ~~Generar las escenas del guion corto (1 min) en proyectos
  que ya tienen escenas solo para el guion largo. Se añade el
  nodo fijo `scenes_short` (paralelo a `scenes`) en el editor de
  grafo y en el runner. Helper `_persist_scenes(...)` reutilizado
  por ambos.~~ **Purgado en v2.1.0**: el runner no existe y la
  página `/scenes` ya cubría guion corto vía el helper de escenas
  per-video del modelo `videos` (introducido en la auditoría de
  roadmap). El QC de short-form exige ≥ 6 escenas (alineado con
  el prompt `scenes`).
- [ ] ~~Sustituir importmap de esm.sh por bundles locales en
  `static/vendor/`~~. **Cancelado**: la dependencia de `esm.sh`
  desapareció con el editor de grafo.
- [x] ~~Añadir tests E2E del runner vía `app.test_client()` que
  verifiquen cambio de estado `idle → running → ok` en
  `node_executions` para los nodos fijos~~. **Purgado en v2.1.0**
  junto con el runner.

### Editor de grafo 2026-09-01 — retirado en v2.1.0

Las tareas marcadas como `[x]` describían el sprint original que
introdujo `profile_graph_nodes`, `node_executions`, los blueprints
huérfanos y los siete endpoints `/profiles/<id>/graph/*` y
`/projects/<id>/run/*`. Tras la auditoría 2026-09-11 esos endpoints
nunca se llegaron a registrar: la sección completa se considera
histórica y se conserva aquí solo para preservar el rastro de
decisiones que motivaron la purga del ADR 2026-09-11.

- [x] Migrar `stage_prompts` por proyecto a `profile_prompts` por
  perfil; migración idempotente en `init_db()` con backup
  `workflow.db.bak` y flag en `_schema_migrations`.
- [x] `resolve_stage_prompt(profile_id, stage)` como única vía de
  lectura; fallback a `config.json`. Refactor de los seis handlers
  para usarla; eliminada la acción POST `save_prompt` y los helpers
  `get_saved_prompt` / `save_stage_prompt` /
  `list_saved_prompts` / `_ensure_stage_prompt` /
  `backfill_stage_prompts`. `STAGE_ALIASES` se mantiene como única
  pieza viva de este sprint: lo usa `resolve_stage_prompt` para
  resolver nombres ambiguos del roadmap.

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

### Auditoría 2026-09-02 — Inversión de layout

- [x] T-LAYOUT-2 — Inversión de T-LAYOUT-1 por preferencia del usuario:
  los proyectos reales (`Todo_sobre_los_Fosiles_1/`,
  `Todo_sobre_los_arboles_gigantes_9/`) vuelven a `projects/`, que
  pasa a estar versionado. `examples/` queda con `Verificacion_pipeline_2/`
  (más su `.zip`) como única referencia canónica del pipeline.
- [x] T-CHORE-1 — `.gitignore` cubre `projects/Verificacion_pipeline_*/`
  y `projects/Verificacion_pipeline_*.zip` para que la salida runtime
  de `verify_project.py` no contamine `git status`. `projects/.gitkeep`
  reescrito para documentar la nueva semántica.
- [x] T-DOC-4 — `AGENTS.md`, `README.md` y `docs/ARCHITECTURE.md`
  alineados: `projects/` versionable con proyectos del usuario;
  `examples/` solo la referencia del pipeline.
- [x] Validación: `python test_core.py` y `python verify_project.py`
  verdes tras la inversión.

### Auditoría 2026-09-02

- [x] T-DOC-1 — `AGENTS.md` actualizado para reflejar la extracción de
  `services/` (T2.1) y `blueprints/` (T2.2) en lugar de declarar el
  monolito como única capa.
- [x] T-LAYOUT-1 — Decisión inicial de mover Fosiles/Arboles/
  Verificacion_pipeline_2 fuera de `projects/`. Invertido
  inmediatamente después por T-LAYOUT-2 (ver bloque anterior).
- [x] T-DOC-2 — `README.md` lista `services/` y `blueprints/` en el
  árbol del proyecto, junto a las tres muestras oficiales en
  `examples/` (Fosiles, Arboles, Pipeline).
- [x] T-DOC-3 — `LICENSE` MIT añadido en la raíz (recomendación de
  `devkit audit`).
- [x] Validación: `python test_core.py` y `python verify_project.py`
  verdes tras el movimiento de proyectos.

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

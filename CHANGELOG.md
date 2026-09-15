# Changelog

Todos los cambios relevantes de Todo Sobre Todo se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
el versionado [Semantic Versioning](https://semver.org/lang/es/).

## [2.0.0] - 2026-09-07

### Breaking

- Esta versión elimina la integración con OpenAI, Anthropic y los
  presets personalizados. La herramienta es **solo modo manual**:
  prepara los prompts SYS + USER listos para copiar en cualquier LLM
  externo (ChatGPT, Claude, Gemini, etc.). Quien necesite la
  integración con API debe quedarse en 1.x.

### Removed

- Proveedores LLM (`openai`, `anthropic`, `custom`) y todo su cableado
  HTTP en `services/llm.py`. El módulo se renombra a
  `services/manual.py` y conserva `call_llm`, `llm_output_is_manual`
  y `_manual_fallback` (este último ya como helper privado, no como
  fallback de error).
- Bloque `llm` de `config.json` (`provider`, `openai`, `anthropic`,
  `active_preset`, `presets`, `temperature`, `max_tokens`).
- Ruta `/settings`, blueprint `blueprints/settings.py` y plantilla
  `templates/settings.html`. La pestaña "Configuración" del nav
  desaparece: no hay nada que configurar en una build manual.
- Función `llm_mode()` y constante `PROVIDER_NAMES` en `app.py`:
  el contexto de plantilla ahora expone una constante `LLM_MODE`
  con el modo manual único.
- Toggle del provider en `test_core.py` (los 4 bloques
  `app.CONFIG["llm"]["provider"] = "manual"` ya no tienen razón de
  ser).

### Changed

- `app.py`: simplificación de `llm_mode()` → constante `LLM_MODE`.
  Logs de arranque pasan de "LLM provider: manual" a "Modo: manual
  (los prompts se copian al LLM externo)".
- `templates/base.html`: el `mode-chip` pasa de ser un enlace a
  `/settings` a ser un `<span>` (sin href) que muestra "Modo manual
  · copias los prompts a tu LLM".
- Las 6 plantillas por etapa (`research`, `concept`, `scripts`,
  `scenes`, `metadata`, `thumbnails`) eliminan la rama
  `{% elif llm.key == 'manual' %}` (siempre verdadera) y simplifican
  la ternaria del botón a `{% if saved %}Regenerar prompt{% else %}Generar prompt{% endif %}`.
- `test_core.py` importa `parse_scenes_json`, `parse_prompt_json` y
  `estimate_duration_seconds` directamente desde `services.parsers`,
  eliminando los re-exports que `app.py` ya no necesita.

### Added

- ADR `2026-09-07 — Modo manual exclusivo` en `docs/DECISIONS.md`
  con contexto, decisión, consecuencias y reversibilidad.
- `config.json:app.version` bumpeado a `2.0.0`. `pyproject.toml`
  igual.

### Migration

- Quien venía usando la API: debe actualizar manualmente sus prompts
  copiando los bloques `## [MODO MANUAL]` a su LLM externo. El
  contrato del output (secciones `## RESUMEN`, `## ÁNGULO`,
  `## HOOK`, etc.) no cambia: cualquier LLM moderno lo entiende.
- Quien guardaba API keys en `.env` o `config.json`: ya no se leen.
  Recomendado retirarlas para evitar secretos huérfanos.

## [Unreleased]

### Added

- **Auditoría completa de prompts del pipeline** (Fases 1–4 del 2026-09-10):
  las 10 claves de `prompts` en `config.json` (research, concept,
  script_long, script_short, scenes, metadata_youtube_long,
  metadata_youtube_short, metadata_facebook_long, metadata_reels_short,
  thumbnail_long, thumbnail_short, **refiner**) se inyectan con el
  perfil activo del proyecto (`mystery_level`, `drama_level`, `tone`,
  `style`, `audience`, `narration_speed`, `platforms`).
- Nuevo módulo `services/templates.py` con `render(text, context)` y
  `render_profile(text, profile)`: mini-motor de plantillas
  `{{path.to.value}}` puro, sin dependencias externas. `RenderReport`
  registra paths desconocidos en `unknown` para diagnóstico silencioso.
- Nueva clave `refiner` en `config.json` con SYS+FORMAT que toma un
  output existente + lista de issues QC + el FORMAT del prompt original
  y devuelve la respuesta corregida solo donde hace falta. Builder
  `app.build_refiner_prompt(profile, stage_label, current_output,
  issues, original_format)` listo para integrarse en una ruta futura.
- Nueva constante compartida `config.visual_style.keywords` (14 keywords
  cinematográficas) reutilizada por los prompts visuales vía
  `{{app.visual_style_keywords}}`. Reemplaza tres listas literales
  duplicadas en `scenes`, `thumbnail_long`, `thumbnail_short`.

### Changed

- `parse_metadata` se refactoriza a dispatcher por plataforma con cuatro
  ramas (`youtube_long`, `youtube_short`, `facebook_long`,
  `reels_short`); cada rama procesa solo los campos que su prompt
  declara y siempre devuelve el dict canónico completo
  (`titles`, `description`, `chapters`, `tags`, `hashtags`,
  `caption`, `hook`, `cta`, `on_screen_text`).
- `resolve_stage_prompt` ahora aplica el render del perfil activo
  antes de devolver (sys, user). Las ediciones del usuario en
  `/profiles/<id>/graph` surten efecto aunque vivan bajo el key del
  roadmap (`scripts`, `metadata`, `thumbnails`); el bug latente que
  hacía caer siempre al fallback de CONFIG queda corregido.
- `_roadmap_instruction_for` prioriza el nombre del roadmap
  (`scripts`, `metadata`, `thumbnails`) y solo después itera las
  alternativas declaradas en `ROADMAP_PROMPT_KEYS`.
- Nuevo dict `STAGE_ALIASES` (`scenes_short → scenes`,
  `scripts → script_long`, `thumbnails → thumbnail_long`) permite que
  el runner del grafo use nombres «humanos» sin perder el prompt
  canónico.
- `build_concept_prompt` inyecta explícitamente los bloques
  `HECHOS CONFIRMADOS`, `TEORÍAS Y VERSIONES`, `FUENTES` y
  `AFIRMACIONES QUE REQUIEREN VERIFICACIÓN` parseados de research.
  El prompt SYS de `concept` exige anclar la tesis en al menos dos
  hechos confirmados y declara las afirmaciones dudosas que NO debe
  usar como base; nuevo bloque `## ANCLAJE EN HECHOS` en su FORMAT.
- `scenes` (SYS) declara arco emocional progresivo: Escena 1 asombro,
  Escena 2 misterio, Escena 3 pregunta visual; las escenas restantes
  deben progresar en tensión, evidencia o escala sin repetir sujetos
  ni composiciones.
- `KNOWN_FIXED_NODE_KEYS`, `DEFAULT_NODE_LABELS`,
  `DEFAULT_NODE_POSITIONS` y `DEFAULT_EDGES` pasan de 10 a 12 nodos
  fijos con los nombres modernos de metadata
  (`metadata_youtube_long`, `metadata_youtube_short`,
  `metadata_facebook_long`, `metadata_reels_short`).
- `_build_user_msg_for_fixed` y `_persist_fixed_result` reescritos:
  cuatro ramas explícitas por cada plataforma de metadata en lugar de
  los dos nodos legacy (`metadata_youtube`/`metadata_shorts`). El
  nodo genérico `thumbnail_long`/`thumbnail_short` mantiene su forma.

### Removed

- Claves legacy `metadata_youtube` y `metadata_shorts` de
  `config.json` (código muerto: ninguna ruta ni perfil las usaba).
  El dict `legacy` interno de `build_metadata_prompt` desaparece.
- Nodos legacy `metadata_youtube` y `metadata_shorts` del
  `KNOWN_FIXED_NODE_KEYS` y de `DEFAULT_NODE_LABELS`. Reemplazados
  por las cuatro keys modernas equivalentes.
- Bloques literales de 14 keywords cinematográficas repetidos en
  `scenes`/`thumbnail_long`/`thumbnail_short`. Sustituidos por la
  variable `{{app.visual_style_keywords}}`.

### Fixed

- **Bug crítico** en `_roadmap_instruction_for`: la DB guardaba los
  prompts per-video con el nombre lógico del roadmap (`scripts`,
  `metadata`, `thumbnails`) pero la función buscaba con las keys de
  CONFIG (`script_long`, `metadata_youtube_long`, etc.). Resultado:
  las ediciones del usuario en `profile_prompts` para esas etapas
  nunca llegaban al runtime, siempre caían al fallback de
  `config.json`. Ahora se prueba primero el key del roadmap.
- Coherencia entre prompt `scenes` (mínimo 6 escenas) y QC de
  short-form (`min_scenes_short` 4→6): ya no discrepan.
- `parse_metadata` ya no reporta campos vacíos por defecto como si
  fueran «parseados mal»: cada plataforma declara los suyos y el
  dict canónico siempre los lleva todos (vacíos los que no apliquen).
- `build_metadata_prompt` ya no oculta el fallo si el platform no es
  uno de los cuatro válidos: ahora hace fallback explícito a
  `metadata_youtube_long` con un warning (antes devolvía vacío).
- `thumbnail_long` (SYS) ya no cierra la frase de la composición
  con un punto suelto tras el bloque de keywords visuales:
  reescrito como un único párrafo cohesionado de 60-100 palabras
  con la guía de estilo integrada.

## [2.1.0] - 2026-09-11

### Removed

- **Editor de grafo + runner del proyecto**: los blueprints
  `blueprints/graph.py` (`graph_bp`) y `blueprints/runner.py`
  (`runner_bp`) existían en `app.py:4261-4265` con un comentario
  marcando que «no se registran a propósito», pero el monolito y
  toda la documentación (`README.md`, `docs/ARCHITECTURE.md`,
  `docs/DECISIONS.md`, `AGENTS.md`, `TASKS.md`, `CHANGELOG.md`) los
  presentaban como features activas. Purga completa:
  - Blueprints: `blueprints/graph.py`, `blueprints/runner.py`.
  - Templates huérfanas: `templates/profile_graph.html`,
    `templates/project_run.html`.
  - JS del editor: `static/graph.js` + `static/graph/` (4 módulos
    ESM, React Flow v12 por importmap desde `esm.sh`).
  - CRUD de nodos en `app.py`: `KNOWN_FIXED_NODE_KEYS`,
    `DEFAULT_NODE_LABELS`, `DEFAULT_NODE_POSITIONS`, `DEFAULT_EDGES`,
    `MAX_OUTPUT_BYTES`, `get_or_create_fixed_graph_nodes`,
    `fetch_graph_nodes`, `fetch_graph_edges_as_eedges`,
    `save_graph_node`, `delete_graph_node`, `update_graph_layout`,
    `_interpolate_inputs`, `_truncate_to_bytes`, `_persist_scenes`,
    `_persist_fixed_result`, `_load_first_script`,
    `_build_user_msg_for_fixed`, `execute_graph_node` (~830 LOC).
  - Parámetro `graph_url` en `_macros.html:prompt_editor` y los
    seis call-sites (`concept`, `metadata`, `scenes`, `thumbnails`,
    `research`, `scripts`). El botón "Editar en el grafo" estaba
    siempre oculto porque `graph_url` nunca se asignaba en el
    contexto del template.
  - Tablas huérfanas `profile_graph_nodes` y `node_executions`
    creadas/dropeadas en cada arranque de `init_db()`: ahora se
    dropean en arranque y se omiten del `SCHEMA`. Las migraciones
    idempotentes mantienen el backup defensivo para BDs legacy que
    pudieran tener restos.
- Bloque "Editor visual de grafo (por perfil)" en `README.md`:
  la sección describía una feature que no estaba en la build.

### Changed

- `app.py`: 4 339 → 3 502 líneas (-19%). El monolito vuelve a
  acercarse al tamaño post-T2.2 (2 477 líneas) declarado en el
  ADR-010. Las funciones puras siguen viviendo en `services/`; los
  blueprints activos son solo `profiles_bp`.
- `docs/ARCHITECTURE.md` reescrito: ya no menciona `graph_bp` /
  `runner_bp` / `profile_graph_nodes` / `node_executions` /
  `templates/profile_graph.html` / `static/graph.js`. La tabla de
  servicios incluye `services/stages.py` (estado per-video), la
  sección de estáticos refleja el JS actual sin dependencias
  externas en runtime.
- `AGENTS.md`: `blueprints/` describe solo `profiles_bp`; `static/`
  describe `app.js` + `copy-fields.js` sin el editor de grafo.
- `ruff check`: 14 errores históricos → 0. 10 auto-fix (`ruff check
  --fix`), 4 manuales (1 `F401`, 3 `F841`).

### Fixed

- `app.py:4257-4258` y `4261-4265`: dos comentarios marcaban rutas
  que ya no existen (`/settings` en `blueprints/settings.py`,
  grafo y runner fuera de scope). Sustituidos por un único
  comentario en la sección de registro de blueprints que explica
  el motivo.
- Drift de `profile_graph.html:12` ("Nueve etapas obligatorias")
  con el número real (12 nodos fijos).

## [1.0.0] - 2026-08-29
### Added

- Importación inicial de Todo Sobre Todo, centro local de planificación
  de contenido audiovisual (Flask + Jinja2 + SQLite).
- Aplicación monolítica `app.py` con flujo TEMA → INVESTIGACIÓN → CONCEPTO →
  GUION → ESCENAS → METADATA → CONTROL DE CALIDAD → EXPORTAR.
- Modos manual y API multi-proveedor (OpenAI, Anthropic, Azure, Ollama,
  LM Studio y presets personalizables vía `config.json`).
- Verificador CLI de calidad (`verify_fosiles.py`) y suite de tests
  (`test_core.py`).
- Perfiles reutilizables de contenido (tipo, audiencia, tono, misterio,
  drama, velocidad, plataformas).
- Exportación de cada proyecto como ZIP con `00_RESUMEN.md`,
  `01_investigacion.md`, guiones, escenas, metadata y JSON
  consolidado.

### Changed

- Adopción de convenciones de Developer-Kit: `.editorconfig`,
  `AGENTS.md`, `TASKS.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`.
- `.gitignore` Python añadido (cubre `__pycache__/`, `workflow.db`,
  virtualenvs, artefactos de build y metadatos de IDE).
- Repositorio inicializado en `main` con `core.autocrlf=input` para
  respetar `end_of_line = lf` del `.editorconfig`.

[Unreleased]: https://github.com/aimanagement14/TST-Control/compare/v2.0.0...HEAD
[1.0.0]: https://github.com/aimanagement14/TST-Control/releases/tag/v1.0.0
[2.0.0]: https://github.com/aimanagement14/TST-Control/releases/tag/v2.0.0
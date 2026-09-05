# Changelog

Todos los cambios relevantes de Todo Sobre Todo se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
el versionado [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Fixed

- **Bug crítico**: las páginas por etapa (research, concept, scripts,
  scenes, metadata, thumbnails) emitían un form con `action=save_prompt`
  que ningún handler en `app.py` procesaba. Resultado: cualquier edición
  en el editor de prompts de las páginas se perdía silenciosamente al
  pulsar "Guardar cambios". El editor de grafo por perfil
  (`/profiles/<id>/graph`) es la única vía para editar prompts (ADR
  2026-09-01), por lo que el botón se sustituye por un enlace
  "Editar en el grafo" en `_macros.html:prompt_editor` y los form inline
  de `scripts.html`, `metadata.html`, `thumbnails.html` se refactorizan
  para usar la macro. Las textareas pasan a `readonly` para evitar
  ediciones accidentales que se perderían.

- **Asimetría del runner**: el runner de grafo sólo persistía escenas
  para el guion largo. Se añade el nodo fijo `scenes_short` (paralelo a
  `scenes`) con su prompt builder, helper `_persist_scenes()` reutilizado
  por ambos, posición default y arista `script_short → scenes_short`. La
  etapa Escenas cubre ahora ambos guiones desde el runner.

- Tabla legacy `prompts` (de la etapa "Prompts visuales" eliminada en
  2026-08-29) anotada en `SCHEMA` con un comment explicando que no se
  escribe y por qué `qc.py` aún la lee.

### Added

- Tests E2E del runner vía `app.test_client()` (`test_runner_renders_for_project`,
  `test_runner_execute_route_returns_json`,
  `test_runner_reset_node_clears_executions`,
  `test_runner_scenes_short_persists_to_short_script`) que cubren el
  ciclo `idle → running → ok` y el render con los 10 nodos fijos.

- Tests para `parse_metadata` con las plataformas nuevas
  `metadata_facebook_long` (prosa continua, sin listas) y
  `metadata_reels_short` (descripción + hashtags + CTA).

- Test unitario `_persist_scenes` que verifica que escribe solo en el
  guion pedido.

- `LICENSE` MIT en la raíz (recomendación de `devkit audit`).
- Logger estructurado `tst` (`logging.basicConfig` con nivel
  configurable vía `TST_LOG_LEVEL`). Los prints del bloque `__main__`
  migran a `log.info` / `log.error`, y los prints de error en
  handlers migran a `log.warning` / `log.exception` para dejar
  trazabilidad antes de abordar `except Exception:` silenciosos
  (T3.1).
- Lockfile reproducible: `requirements.in` (specs de alto nivel) +
  `requirements.lock` (versiones pinned de todas las transitivas,
  generado con `pip-tools`) + `requirements.txt` (copia del lock
  para `pip install -r` directo en CI y dev).
- Workflow de CI (`.github/workflows/ci.yml`): corre `test_core.py`
  y `verify_project.py` en Python 3.13 sobre `push` y
  `pull_request` a `main`. Badge en `README.md`.
- `services/` con parsers puros, llamadas LLM y QC. Extraído del
  monolito como PoC (ADR-010). `app.py` re-exporta los símbolos
  para preservar la API existente.
- `blueprints/graph.py` (`graph_bp`) y `blueprints/runner.py`
  (`runner_bp`) con las 7 rutas aisladas del editor de grafo y del
  runner. Endpoints con prefijo del blueprint (`graph.*`,
  `runner.*`). Local imports en handlers para romper ciclos con
  `app.py`.

### Changed

- **Inversión de layout** (sustituye a la decisión previa en este
  mismo `[Unreleased]`): `examples/` ya no guarda los proyectos
  reales del usuario. Ahora contiene solo la **referencia canónica
  del pipeline** (`Verificacion_pipeline_2/` + `.zip`), snapshot del
  proyecto sintético que `verify_project.py` regenera cada vez. Los
  proyectos reales (`Todo_sobre_los_Fosiles_1/`,
  `Todo_sobre_los_arboles_gigantes_9/`) vuelven a `projects/`, que
  pasa a estar **versionado**. La salida runtime de `verify_project.py`
  (`projects/Verificacion_pipeline_2*`) queda cubierta por `.gitignore`
  para no contaminar `git status`. `AGENTS.md`, `README.md`,
  `docs/ARCHITECTURE.md` y `projects/.gitkeep` reflejan la nueva
  semántica.
- `app.secret_key` deja de leerse de `config.json` (que ya no la
  contiene). Ahora se lee de la variable de entorno
  `FLASK_SECRET_KEY`, con fallback a `config.json` solo para dev.
  Sin variable definida, `app.py` falla con `RuntimeError` claro al
  arrancar.
- `PRODUCT.md` y `README.md` alinean el pipeline a las 8 etapas
  reales (`research → concept → scripts → scenes → metadata →
  thumbnails → qc → export`). Las menciones históricas a la
  reducción de 8 a 7 etapas (CHANGELOG, docs/DECISIONS) se
  mantienen como contexto de la decisión 2026-08-29.
- `static/graph.js` se divide en 4 módulos ESM bajo `static/graph/`
  (`nodes.js`, `api.js`, `layout.js`, `index.js`). `graph.js`
  queda como re-export de 6 líneas para preservar el `<script
  src="graph.js">` de las plantillas. Cada módulo tiene una
  responsabilidad única: componentes UI, backend client + stubs,
  layout helpers, y entry que monta la app.
- `examples/` recibe la muestra oficial versionada
  `Todo_sobre_los_Fosiles_1/` (con su `.zip`). `projects/`
  queda como directorio generado por la app en runtime, con
  `.gitkeep` que lo explica.

### Fixed

- **Seguridad**: `config.json` ya no contiene la clave de Flask en
  claro. Se sustituye por `FLASK_SECRET_KEY` (variable de entorno)
  con fallback a `config.json` solo para dev. `README.md` documenta
  cómo generar la clave con
  `python -c 'import secrets; print(secrets.token_hex(32))'`.

_Entradas previas del [Unreleased] abiertas antes del editor de grafo:_

### Added

- Editor visual de grafo por perfil (`/profiles/<id>/graph`): React
  Flow v12 cargado por importmap desde `esm.sh` (sin build step, sin
  dependencias NPM). Nueve nodos fijos pre-creados (research, concept,
  script_long, script_short, scenes, metadata_youtube, metadata_shorts,
  thumbnail_long, thumbnail_short), posiciones editables con drag &
  drop, conexiones libres, posibilidad de añadir nodos custom con sus
  propios prompts SYS y USER. Las posiciones se persisten con debounce
  de 600 ms.
- Runner sobre proyecto (`/projects/<id>/run`): misma vista de
  grafo, ejecución nodo a nodo con un clic. Los nodos fijos reutilizan
  los builders y parsers existentes; los custom hacen `call_llm`
  directo interpolando `{{ inputs.<key> }}` con el output de nodos
  previos. Cada ejecución se persiste en `node_executions` con su
  estado (`idle`/`running`/`ok`/`error`) y duración.
- Tablas nuevas `profile_graph_nodes` (con `is_fixed`, posiciones y
  `inputs_json`) y `node_executions` (estado, output, duración).
- Funciones nuevas: `resolve_stage_prompt`, `save_profile_prompt`,
  `list_profile_prompts`, `get_default_prompts_from_config`,
  `execute_graph_node`, y el conjunto de helpers del grafo
  (`get_or_create_fixed_graph_nodes`, `fetch_graph_nodes`,
  `fetch_graph_edges_as_eedges`, etc.).
- Siete rutas nuevas: `/profiles/<id>/graph` (GET),
  `/profiles/<id>/graph/save-node` (POST),
  `/profiles/<id>/graph/delete-node` (POST),
  `/profiles/<id>/graph/layout` (POST), `/projects/<id>/run` (GET),
  `/projects/<id>/run/execute` (POST),
  `/projects/<id>/run/reset-node` (POST).

### Changed

- Los prompts SYS + USER ya no viven a nivel de proyecto sino de
  perfil, en `profile_prompts` (`UNIQUE(profile_id, stage)`).
  `resolve_stage_prompt(profile_id, stage)` es la única vía de lectura,
  con fallback a `config.json`. Cambiar un prompt en un perfil lo
  cambia para todos los proyectos que lo usen.
- Las páginas por etapa (research, concept, scripts, scenes,
  metadata, thumbnails) ya no exponen el formulario «Guardar prompt»:
  la edición vive en el grafo. Siguen mostrando el prompt generado al
  vuelo y guardan el output del LLM en la tabla correspondiente.
- Página de proyecto (`templates/project.html`): el panel
  «Prompts guardados» pasa a ser un enlace al editor de grafo del
  perfil.

### Removed

- Tabla legacy `stage_prompts`. Sus filas se migran automáticamente
  a `profile_prompts` la primera vez que arranca la app (con backup
  `workflow.db.bak` controlado por `_schema_migrations`).
- Ruta `POST /projects/<id>/stage-prompts/backfill` y su acción
  asociada (la regeneración de prompts ahora vive en el grafo).
- Helpers `get_saved_prompt`, `save_stage_prompt`,
  `list_saved_prompts`, `_ensure_stage_prompt`,
  `_stage_context`.

_Entradas previas del [Unreleased] abiertas antes del editor de grafo:_

### Added

- Nueva etapa **Miniaturas** entre `Metadata` y `Control de calidad`, con dos
  paneles (5 min en 16:9 y 1 min en 9:16). Cada panel genera un prompt visual
  cinematográfico fijo listo para Midjourney / Flux / DALL-E, sin texto
  overlay y coherente con la guía visual del proyecto (Cinematic
  Hyperrealism, Orange & Teal, etc.). La etapa se considera completa
  cuando ambas miniaturas están guardadas.
- Nueva tabla `thumbnail_records` (`UNIQUE(project_id, script_type)`) y
  parser `parse_thumbnail` dedicado al bloque `## MINIATURA`.

### Changed

- Renumeración en el ZIP exportado: aparece `06_thumbnails/`,
  `07_prompts_usados.md` y `08_paquete_completo.json` (antes 06 y 07).
- El pipeline pasa de 7 a 8 etapas; QC pasa a `08`.
- `templates/project.html` ahora muestra hasta 9 prompts guardados y dos
  entradas más (Miniatura 5 min, Miniatura 1 min).

- Barra de etapas persistente (tira de película) en todas las páginas de
  proyecto: posición actual, etapas completadas, progreso y duración
  estimada del guion frente al objetivo del formato.
- Navegación entre etapas al pie de cada página (anterior / siguiente) y
  «siguiente acción» calculada en el dashboard y en la hoja de ruta.
- Botón de copiar con confirmación en todos los prompts, en los guiones
  guardados y en la metadata (descripción, tags, hashtags, caption).
- Contadores en vivo de palabras y duración estimada bajo cada área de
  pegado, con el rango objetivo del formato marcado en color.
- `static/app.js`: portapapeles con reserva para contextos no seguros,
  contadores, deslizadores con lectura numérica y cierre de avisos.
- Indicador permanente del modo de generación (manual o API) en la
  cabecera, enlazado a Configuración.

### Changed

- Rediseño visual completo: paleta de grafito azulado, tipografía técnica
  condensada, cifras monoespaciadas tabulares y color como señal de estado
  (ámbar = te toca, verde = listo, rojo = bloquea, azul = información).
- Etapas con contenido guardado muestran primero el contenido y esconden
  el área de pegado en un desplegable (guiones, metadata).
- Estados del proyecto en lenguaje de usuario («Listo para exportar») en
  lugar de los valores internos de base de datos.
- Metadata: el guion base se preselecciona según la plataforma y cada
  panel muestra los campos propios del formato (caption, hook y textos en
  pantalla en vertical; títulos, capítulos y tags en YouTube).
- **Eliminada la etapa «Prompts visuales»** por ser redundante con
  Escenas (cada escena ya almacena un `IMAGEN` cinematográfico
  completo). El pipeline pasa de 8 a 7 etapas; las exportaciones se
  renumeran (`05_metadata/`, `06_prompts_usados.md`,
  `07_paquete_completo.json`).
- La etapa Escenas exige escenas para **ambos guiones** (largo y
  corto) antes de marcar la celda como lista; antes bastaba con
  escenas en uno solo para considerarla completa.
- Tabs de selección de guion en Escenas: el activo se calcula con
  `namespace()` (Jinja2) para que `script_id` de la URL se respete
  siempre; el tab activo se distingue con borde inferior ámbar y
  atenuado el resto.
- Control de calidad: avisos ordenados por severidad, nombres de etapa y
  campo legibles, marcas de tiempo del último análisis y estado propio
  para «sin avisos».
- Mensajes del QC con formato de tiempo `MM:SS` y guiones identificados
  como «(5 min)» / «(1 min)».
- Nivel base de accesibilidad: enlace para saltar al contenido, foco
  visible, `aria-current` en la navegación, avisos con `role="status"` y
  respeto de `prefers-reduced-motion`.
- `test_core.py` añadía `gc.collect()` entre tests QC/export para
  evitar `PermissionError` en la limpieza de `tempfile.TemporaryDirectory`
  en Windows (SQLite conserva el handle del `.db` aunque el `with`
  cierre la conexión).
- Documentación: `docs/ARCHITECTURE.md` y `docs/DECISIONS.md` pasan de
  plantilla vacía a una descripción completa de módulos, modelo de
  datos y decisiones técnicas.
- `TASKS.md` actualizado con el backlog real.

### Fixed

- El área de pegado ya no se rellena con el texto de «[MODO MANUAL]»
  cuando la llamada al LLM no devuelve contenido.
- `copyToClipboard()` en Concepto tomaba el primer formulario de la
  página, no el del prompt, así que copiaba en vacío.
- Investigación fallaba al generar el prompt porque la plantilla contaba
  `facts` y `sources` sin comprobar que existieran.
- `run_qc` + `qc()` solo movían el proyecto a `status='ready'` cuando
  no había issues de ningún tipo. Ahora los `warning` e `info` no
  bloquean la transición: solo los `error` lo hacen. Los proyectos
  completos pasan a `ready` aunque el QC detecte avisos.
- README y `templates/export.html` anunciaban `07_paquete_completo.json`,
  pero el código generaba `08_paquete_completo.json` con un fichero
  previo `07_prompts_usados.md`. Documentación y plantilla alineadas
  con la estructura real.
- `verify_fosiles.py` asumía que el proyecto con `id=1` existía y
  fallaba con 404 sobre una base de datos limpia. Ahora crea el
  proyecto reutilizando el perfil por defecto si hace falta.
- `_stage_context()` reasignaba `ctx["research"]` en tres ramas
  distintas (`concept`, `script_*`, `concept` de nuevo). Reescrito para
  cargar cada contexto una sola vez según la etapa.
- `build_metadata_prompt()` mostraba `profile['platforms']` como JSON
  crudo. Ahora se parsea y se presenta como lista legible.
- `import urllib.request` se hacía dentro de `call_llm`. Movido al
  bloque de imports del módulo.
- Footer sin margen superior visible por orden de declaración CSS
  (margin-top se sobrescribía con margin-left/right: auto). Corregido.

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

[Unreleased]: https://github.com/aimanagement14/TST-Control/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/aimanagement14/TST-Control/releases/tag/v1.0.0
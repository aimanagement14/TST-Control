# Architecture

Describe la estructura general del proyecto, sus módulos y los límites
entre ellos.

## Visión general

Todo Sobre Todo es una aplicación Flask monolítica, sin ORM, sin frontend
compilado y sin microservicios. Todo el flujo vive en `app.py` y la
persistencia es un único archivo SQLite (`workflow.db`).

La intención es que el ciclo completo — desde un tema hasta un paquete
listo para producción — se pueda ejecutar localmente, auditar con un par
de tests y desplegar con `waitress` en Windows o el dev-server de Flask
en cualquier plataforma.

`projects/` contiene los proyectos reales del usuario y se versiona
(cada uno en `projects/<safe_name>_<id>/` más, opcionalmente,
`projects/<safe_name>_<id>.zip`). El output runtime de `verify_project.py`
(`projects/Verificacion_pipeline_2*`) está cubierto por `.gitignore` para
no contaminar `git status`. `examples/` guarda la referencia canónica del
pipeline: hoy solo `Verificacion_pipeline_2/` (y su `.zip`), snapshot del
proyecto sintético que `verify_project.py` regenera cada vez que corre.

```
┌─────────────────────────────────────────────────────────────┐
│                       Navegador                             │
└─────────────────────────────────────────────────────────────┘
                          │  HTTP
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Flask app (app.py + blueprints/)                           │
│  ┌────────────┐ ┌───────────────────────┐ ┌──────────────┐  │
│  │  Rutas     │ │  Blueprints (T2.2)    │ │  Re-exports  │  │
│  │  (vistas)  │ │  graph_bp / runner_bp │ │  de services │  │
│  └────────────┘ └───────────────────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  services/ (T2.1) — funciones no-HTTP                       │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │   parsers    │  │     llm      │  │       qc          │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │  sqlite3
                          ▼
                ┌─────────────────────┐
                │   workflow.db       │
                └─────────────────────┘
                          │
                          ▼
                ┌─────────────────────┐
                │  projects/<name>.zip│
                └─────────────────────┘
```

## Módulos

### `app.py`

Monolito Flask que sigue siendo la pieza central del proyecto
(ADR-001), pero ahora **delega** parte de su trabajo a `services/`
y `blueprints/`. Conserva internamente:

| Sección | Responsabilidad |
|---------|-----------------|
| Configuración | Carga `config.json`, instancia Flask, sirve `/favicon.ico`, registra los blueprints (`graph_bp`, `runner_bp`). |
| Base de datos | Define el `SCHEMA` (13 tablas tras el editor de grafo), expone `get_db()` con rows como `sqlite3.Row` y `init_db()` para sembrar el perfil por defecto y aplicar migraciones idempotentes controladas por `_schema_migrations`. |
| Utilidades | `now_iso`, `count_words`, `estimate_duration_seconds`, carga de perfil/proyecto, resolución de prompt por perfil (`resolve_stage_prompt`) con render del perfil activo vía `services.templates`. |
| LLM client | Re-exporta `call_llm`, `_manual_fallback`, `llm_output_is_manual` desde `services.llm` (T2.1). |
| Parsers | Re-exporta `parse_research`, `parse_concept`, `parse_script`, `parse_scenes_json`, `parse_scenes_tst`, `parse_prompt_json`, `parse_metadata` (dispatcher por plataforma), `parse_thumbnail` desde `services.parsers` (T2.1). |
| QC | Re-exporta `run_qc` y `save_qc_issues` desde `services.qc` (T2.1). |
| Editor de grafo | Resolución y guardado de prompts por perfil (`save_profile_prompt`, `list_profile_prompts`, `get_default_prompts_from_config`), 12 nodos fijos pre-creados (`get_or_create_fixed_graph_nodes`), `STAGE_ALIASES` para resolver nombres ambiguos del runner. Las rutas HTTP viven ahora en `blueprints/graph.py`. |
| Runner | Lógica de `execute_graph_node` y helpers. Las rutas HTTP viven en `blueprints/runner.py`. |
| Rutas | Vistas por etapa, dashboard, perfiles (excepto graph), settings y export. |
| Contexto plantilla | Inyecta `app_name`, `app_tagline`, `app_version` en cada render. |
| Refiner post-QC | `build_refiner_prompt(profile, stage_label, current_output, issues, original_format)` toma un output existente + issues QC y devuelve un SYS+USER listo para regenerar solo lo marcado por QC. |
| Arranque | `python app.py` (dev) o `python app.py --prod` (waitress). |

### `services/`

Funciones puras o casi-puras extraídas de `app.py` durante T2.1.
**No** dependen de Flask context (`request`, `g`, `session`).
`services.llm` y `services.qc` hacen local import de `app` para
leer `CONFIG`, `get_db` y compañía, evitando ciclos.

| Archivo | Funciones |
|---------|-----------|
| `services/parsers.py` | `parse_research`, `parse_concept`, `parse_script`, `parse_scenes_json`, `parse_scenes_tst`, `parse_scenes`, `parse_prompt_json`, `parse_metadata` (dispatcher), `parse_thumbnail`, `count_words`, `estimate_duration_seconds`. |
| `services/templates.py` | `render`, `render_profile`, `profile_context`, `app_context`, `RenderReport`. Mini-motor `{{path.to.value}}` para inyectar el perfil activo en los prompts SYS. |
| `services/llm.py` | `call_llm`, `_manual_fallback`, `llm_output_is_manual`. (Renombrado a `services/manual.py` en v2.0; las ramas API se eliminaron.) |
| `services/qc.py` | `run_qc`, `save_qc_issues`. |
| `services/sync.py` | `safe_project_dir`, `delete_project_folder`, `sync_project_folder`, `sync_project_stages_for_project`. Sincronización de la carpeta del proyecto. |

### `blueprints/`

Blueprints Flask extraídos de `app.py` durante T2.2. Cada
blueprint declara su `url_prefix` y los handlers usan local import
de `app` para resolver helpers de dominio sin ciclos.

| Blueprint | Prefijo | Rutas |
|-----------|---------|-------|
| `blueprints/graph.py` (`graph_bp`) | `/profiles` | GET `/<id>/graph`, POST `/<id>/graph/save-node`, POST `/<id>/graph/delete-node`, POST `/<id>/graph/layout`. |
| `blueprints/runner.py` (`runner_bp`) | `/projects` | GET `/<id>/run`, POST `/<id>/run/execute`, POST `/<id>/run/reset-node`. |

### `config.json`

Toda la configuración editable en runtime vive aquí:

- `app`: nombre, tagline, versión.
- `prompts`: `system` + `format` por etapa (`research`, `concept`,
  `script_long`, `script_short`, `scenes`,
  `metadata_youtube_long`, `metadata_youtube_short`,
  `metadata_facebook_long`, `metadata_reels_short`,
  `thumbnail_long`, `thumbnail_short`, `refiner`). Cada SYS arranca
  con un bloque `{{profile.*}}` que se sustituye en runtime con los
  valores del perfil activo del proyecto (mystery_level, drama_level,
  tone, style, audience, narration_speed, platforms).
- `visual_style.keywords`: lista única de 14 keywords cinematográficas
  que los prompts visuales referencian vía `{{app.visual_style_keywords}}`.
- `qc.checks`: umbrales de palabras, duraciones objetivo, mínimo de
  fuentes, mínimo de escenas (long 6, short 6), umbral de repetición.
- `ui`: colores y paginación.

### Plantillas (`templates/`)

Plantillas Jinja2, una por vista, todas extienden `base.html`. Renderizan
los prompts guardados, exponen los formularios de "pegar respuesta del
LLM" y muestran los resúmenes del proyecto. Auto-escape activado por
defecto (Flask), no se hace `Markup()` en ningún punto.

### Estáticos (`static/`)

Un único `style.css` (≈610 líneas tras el editor de grafo) con variables
CSS para tema oscuro y componentes: cards, formularios, grid de proyectos,
etapas, QC, presets, flash messages, además del chrome del editor de
grafo y los estados visuales de los nodos (idle / running / ok / error).
No se usa Tailwind ni preprocesadores.

El editor visual se entrega como módulo ESM en `static/graph.js` y se
carga por importmap desde `esm.sh` (`@xyflow/react@12.11.6`,
`react@18.3.1`, `react-dom@18.3.1`). El CSS de React Flow se enlaza
también desde `esm.sh`. Es la única dependencia externa en runtime y
solo se solicita al abrir `/profiles/<id>/graph` o
`/projects/<id>/run`; el resto de la app no hace llamadas salientes.

### Tests

- `test_core.py`: tests de parsers, utilidades, motor de plantillas,
  QC engine, dispatcher de metadata, refiner post-QC, persistencia de
  grafo y export. Sustituye `DB_PATH` por una ruta temporal durante
  los tests QC/export.
- `verify_project.py`: smoke test end-to-end que ejecuta el flujo
  completo contra `app.test_client()` con datos simulados. Crea un
  proyecto sintético con `PROJECT_ID=2` si no existe. Su salida se
  regenera en `projects/Verificacion_pipeline_2/` y queda cubierta
  por `.gitignore`; el snapshot canónico de esa referencia vive en
  `examples/Verificacion_pipeline_2/`.

## Modelo de datos

13 tablas. Las entidades centrales (`projects`, `research`, `concept`,
`scripts`, `scenes`, `metadata_records`, `thumbnail_records`) tienen
`project_id` con `ON DELETE CASCADE`. Los prompts viven a nivel de
perfil en `profile_prompts` (`UNIQUE(profile_id, stage)`) y se
resuelven con `resolve_stage_prompt()`, que primero busca la fila por
el nombre lógico del roadmap (`scripts`, `metadata`, `thumbnails`,
etc.), luego itera las alternativas declaradas en `ROADMAP_PROMPT_KEYS`
y finalmente cae a `config.json`. Antes de devolver, aplica el motor
de plantillas `{{profile.*}}` / `{{app.*}}` contra el perfil activo.

El grafo visual persiste en `profile_graph_nodes`
(`UNIQUE(profile_id, node_key)`, `is_fixed` distingue los 12 nodos
pre-creados de los custom) y `node_executions` registra cada ejecución
por proyecto con su output, estado y duración.

`scripts.type` distingue `long` (5 min) de `short` (1 min).
`scenes.script_id` vincula cada escena con su guion.
`metadata_records.platform` admite `youtube_long`, `youtube_short`,
`facebook_long`, `reels_short`. El parser es un dispatcher por
plataforma (`services.parsers.parse_metadata`) que siempre devuelve el
dict canónico completo.
`thumbnail_records.script_type` distingue `long` (16:9) de `short` (9:16).
Las cuatro con `UNIQUE(project_id, type/platform/script_type)` para
impedir duplicados.

## Flujo de datos

1. El usuario crea un proyecto (`POST /projects/new`) → `status='research'`.
2. Los prompts SYS + USER del proyecto los resuelve
   `resolve_stage_prompt(project.profile_id, stage)`. Primero busca en
   `profile_prompts` por el nombre lógico del roadmap, luego por las
   keys alternativas en `ROADMAP_PROMPT_KEYS`, finalmente en
   `config.json`. Antes de devolver, aplica
   `services.templates.render_profile(sys, profile)` para sustituir
   `{{profile.mystery_level}}`, `{{profile.tone}}`, `{{app.name}}`,
   `{{app.visual_style_keywords}}`, etc. Esto significa que cualquier
   proyecto que use el mismo perfil comparte sus prompts y hereda su
   voz editorial en runtime.
3. Cada etapa expone `generate_prompt` (muestra los prompts) y `save`
   (persiste la respuesta parseada del LLM en su tabla final).
4. `QC` (`POST /projects/<id>/qc`) corre `run_qc` y mueve el proyecto a
   `status='ready'` cuando no hay errores (warnings/infos son tolerables).
5. Si el QC detecta issues, el builder opcional
   `build_refiner_prompt(profile, stage_label, current_output, issues,
   original_format)` produce un SYS+USER listo para regenerar solo las
   secciones marcadas. La integración con la UI queda pendiente.
6. `Export` (`POST /projects/<id>/export`) genera el ZIP y lo envía
   como `send_file(as_attachment=True)`.

## Editor de grafo por perfil

Dos páginas nuevas extienden el flujo clásico sin romperlo.

`/profiles/<id>/graph` — Editor visual (estilo n8n) donde cada nodo es
uno de los **doce** nodos fijos del pipeline (`research`, `concept`,
`script_long`, `script_short`, `scenes`, `scenes_short`,
`metadata_youtube_long`, `metadata_youtube_short`,
`metadata_facebook_long`, `metadata_reels_short`, `thumbnail_long`,
`thumbnail_short`) más los nodos custom que el usuario añada. Cada nodo expone sus prompts SYS y USER,
un nombre editable y conexiones hacia otros nodos (los custom pueden
recibir como contexto el output de cualquier nodo previo). El grafo
carga `@xyflow/react` por importmap, persiste posiciones con un debounce
de 600 ms y guarda los prompts vía `POST /graph/save-node` y
`/graph/layout`. Los nombres ambiguos del runner
(`scenes_short`, `scripts`, `thumbnails`) se resuelven vía
`STAGE_ALIASES` al prompt canónico.

`/projects/<id>/run` — Runner que instancia el mismo grafo sobre un
proyecto. El clic en "Ejecutar" de un nodo llama a
`POST /run/execute`, que delega en `execute_graph_node()`: para los
nodos fijos reutiliza los builders y parsers existentes (misma ruta de
generación y persistencia que la página clásica por etapa); para los
custom llama al LLM directo, interpolando `{{ inputs.<key> }}` con los
outputs previos y guardando el resultado en `node_executions`. Cada
nodo muestra su estado (`idle / running / ok / error`) en una esquina,
codificado con las variables CSS del tema.

Las páginas clásicas de cada etapa siguen funcionando: cuando el
usuario genera o guarda contenido allí, los prompts reales son los
del perfil (vía `resolve_stage_prompt`), por lo que el editor visual
queda como única fuente de edición y las páginas por etapa son una
vista enfocada de la misma información.

## Límites y dependencias externas

- **LLM opcional**: el modo manual no hace ninguna llamada saliente.
  A partir de v2.0 el modo manual es el único modo soportado (ver
  ADR 2026-09-07); las versiones 1.x incluían OpenAI, Anthropic y
  presets personalizados.
- **Sin JS de build**: el único JS embebido está en `research.html` y
  `concept.html` para `navigator.clipboard`. No hay bundler.
- **Sin base de datos externa**: SQLite, foreign keys activadas.

## Decisiones

Consulta `docs/DECISIONS.md` para el detalle de las decisiones técnicas.

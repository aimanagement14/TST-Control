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

```
┌─────────────────────────────────────────────────────────────┐
│                       Navegador                             │
└─────────────────────────────────────────────────────────────┘
                          │  HTTP
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Flask app (app.py)                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │   Rutas      │  │   Parsers    │  │  LLM client       │  │
│  │  (vistas)    │  │              │  │  (manual / API)   │  │
│  └──────────────┘  └──────────────┘  └───────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  QC engine   │  │  Export ZIP  │  │  Prompt builder   │  │
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

Único módulo Python de la aplicación. Se organiza internamente en
secciones marcadas con comentarios `---`:

| Sección | Responsabilidad |
|---------|-----------------|
| Configuración | Carga `config.json`, instancia Flask, sirve `/favicon.ico`. |
| Base de datos | Define el `SCHEMA` (10 tablas), expone `get_db()` con rows como `sqlite3.Row` y `init_db()` para sembrar el perfil por defecto. |
| Utilidades | `now_iso`, `count_words`, `estimate_duration_seconds`, carga de perfil/proyecto/prompt guardado. |
| Auto-prompt | `_STAGE_BUILDERS` + `_ensure_stage_prompt` que regenera y guarda los prompts canónicos cuando una etapa se persiste por primera vez. |
| LLM client | `call_llm` con cuatro proveedores (`manual`, `openai`, `anthropic`, `custom`). Resuelve un preset activo sobre el bloque legacy. |
| Parsers | `parse_research`, `parse_concept`, `parse_script`, `parse_scenes_json`, `parse_prompt_json`, `parse_metadata`. Toleran respuestas del LLM con prosa alrededor. |
| QC | `run_qc` (lista de tuplas `stage/severity/message/field`) + `save_qc_issues`. |
| Rutas | Una vista por etapa + dashboard + perfiles + settings + export. |
| Contexto plantilla | Inyecta `app_name`, `app_tagline`, `app_version` en cada render. |
| Arranque | `python app.py` (dev) o `python app.py --prod` (waitress). |

### `config.json`

Toda la configuración editable en runtime vive aquí:

- `app`: nombre, tagline, versión, `secret_key`.
- `llm`: provider, bloques legacy `openai` / `anthropic`, presets,
  temperatura, max_tokens.
- `prompts`: `system` + `format` por etapa (`research`, `concept`,
  `script_long`, `script_short`, `scenes`, `prompts`,
  `metadata_youtube`, `metadata_shorts`).
- `qc.checks`: umbrales de palabras, duraciones objetivo, mínimo de
  fuentes, mínimo de escenas, umbral de repetición.
- `ui`: colores y paginación.

### Plantillas (`templates/`)

Plantillas Jinja2, una por vista, todas extienden `base.html`. Renderizan
los prompts guardados, exponen los formularios de "pegar respuesta del
LLM" y muestran los resúmenes del proyecto. Auto-escape activado por
defecto (Flask), no se hace `Markup()` en ningún punto.

### Estáticos (`static/`)

Un único `style.css` (≈480 líneas) con variables CSS para tema oscuro y
componentes: cards, formularios, grid de proyectos, etapas, QC, presets,
flash messages. No se usa Tailwind ni preprocesadores.

### Tests

- `test_core.py`: tests de parsers, utilidades, QC engine y export.
  Sustituye `DB_PATH` por una ruta temporal durante los tests QC/export.
- `verify_fosiles.py`: smoke test end-to-end que ejecuta el flujo
  completo contra `app.test_client()` con datos simulados. Crea el
  proyecto si no existe.

## Modelo de datos

10 tablas. Las cinco entidades centrales (`projects`, `research`,
`concept`, `scripts`, `scenes`, `prompts`, `metadata_records`) tienen
`project_id` con `ON DELETE CASCADE`. `stage_prompts` almacena los
prompts SYS + USER editados por etapa (`UNIQUE(project_id, stage)`).

`scripts.type` distingue `long` (5 min) de `short` (1 min).
`metadata_records.platform` distingue `youtube` de `shorts`. Ambas con
`UNIQUE(project_id, type/platform)` para impedir duplicados.

## Flujo de datos

1. El usuario crea un proyecto (`POST /projects/new`) → `status='research'`.
2. Cada etapa expone `generate_prompt` (no destructivo, muestra los
   prompts y permite pegarlos en un LLM externo) y `save` (persiste la
   respuesta parseada del LLM).
3. Tras `save`, `_ensure_stage_prompt` regenera y guarda el prompt
   canónico si la etapa todavía no tiene uno.
4. `QC` (`POST /projects/<id>/qc`) corre `run_qc` y mueve el proyecto a
   `status='ready'` cuando no hay errores (warnings/infos son tolerables).
5. `Export` (`POST /projects/<id>/export`) genera el ZIP y lo envía
   como `send_file(as_attachment=True)`.

## Límites y dependencias externas

- **LLM opcional**: el modo manual no hace ninguna llamada saliente.
  En modo API se intenta primero el SDK de Anthropic, si está
  instalado, y se hace fallback a `urllib.request` contra la API REST
  de Anthropic o cualquier endpoint OpenAI-compatible.
- **Sin JS de build**: el único JS embebido está en `research.html` y
  `concept.html` para `navigator.clipboard`. No hay bundler.
- **Sin base de datos externa**: SQLite, foreign keys activadas.

## Decisiones

Consulta `docs/DECISIONS.md` para el detalle de las decisiones técnicas.

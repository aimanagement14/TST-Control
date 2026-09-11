# AGENTS

Guía para agentes de IA que trabajan en este proyecto.

## Convenciones

- Stack: **Python 3.13 + Flask 3 + Jinja2 + SQLite** (sin ORM), frontend sin build
  step (`static/app.js`, `static/graph.js`, importmap a `esm.sh`).
- Type hints donde aporten valor. Evitar `Any` salvo en bordes justificados
  (parsing LLM, JSON externo).
- Funciones pequeñas y con responsabilidad única. Un módulo = una responsabilidad.
- Sin dependencias nuevas sin motivo: `requirements.txt` cubre Flask + waitress.
- Documentar solo cuando aporte valor: nada de docstrings vacíos ni comentarios
  redundantes.
- UI y copy en español por defecto (configurable por preset LLM).

## Estructura

- `app.py` — pieza central del monolito (ADR-001): rutas clásicas por etapa,
  configuración, gestión de BD, registro de blueprints. Conserva además los
  builders/persistencia de etapas; las funciones puras viven fuera (ver
  `services/` y `blueprints/`).
- `services/` — funciones puras extraídas en T2.1 (parsers, `call_llm`, QC,
  `sync`, `templates`). **No** dependen de `request`/`g`/`session`.
  Cubiertas por `test_core.py`.
  - `parsers.py` — parsers de respuestas LLM; incluye `parse_metadata`
    refactorizado a dispatcher por plataforma (`youtube_long`,
    `youtube_short`, `facebook_long`, `reels_short`).
  - `templates.py` — mini-motor de plantillas `{{path.to.value}}` puro,
    usado por `resolve_stage_prompt` para inyectar el perfil activo en
    los prompts SYS/USER.
  - `qc.py` — reglas QC; `error` bloquea la transición a `ready`,
    `warning`/`info` no.
- `blueprints/` — `profiles_bp` con las rutas `/profiles` extraído del
  monolito. Cada blueprint declara su `url_prefix` y usa local imports para
  evitar ciclos con `app`.
- `templates/` — Jinja2. `_macros.html`, `_rail.html`, `_stepper.html` para
  piezas reutilizables; el resto son páginas por etapa.
- `static/` — JS/CSS sin bundler. `app.js` para chrome general y `copy-fields.js`
  para el copy/paste de prompts. Sin editor de grafo en runtime.
- `config.json` — única fuente para prompts SYS/USER, presets LLM, umbrales
  QC y tema visual. Los prompts referencian el perfil activo vía
  `{{profile.tone}}`, `{{profile.mystery_level}}`, etc., y comparten
  las keywords cinematográficas vía `{{app.visual_style_keywords}}`. No se
  mueve a YAML/ENV sin motivo.
- `workflow.db` — SQLite. Migraciones controladas por `_schema_migrations`
  (idempotentes).
- `projects/` — proyectos reales del usuario, **versionados**. Cada uno vive
  en `projects/<safe_name>_<id>/` (carpeta sincronizada con
  `sync_project_folder()`) y, opcionalmente, `projects/<safe_name>_<id>.zip`.
- `examples/` — referencia canónica del pipeline. Hoy contiene solo
  `Verificacion_pipeline_2/` (y su `.zip`), snapshot del proyecto sintético
  que `verify_project.py` regenera cada vez que corre.
- `test_core.py` — parsers, QC, utilidades, motor de plantillas, prompts
  por perfil, dispatcher de metadata, refiner post-QC, CRUD de grafo.
- `verify_project.py` — verificación end-to-end con datos simulados de LLM
  (`PROJECT_ID = 2`, crea proyecto sintético si no existe). Su salida
  (`projects/Verificacion_pipeline_2*`) está cubierta por `.gitignore`.
- `docs/ARCHITECTURE.md` y `docs/DECISIONS.md` — las decisiones técnicas y
  de arquitectura viven ahí, no en comentarios sueltos.

## Backend

- `get_db()` cachea la conexión en `flask.g` durante el ciclo de petición;
  `close_db` (teardown) la cierra. Fuera de contexto (CLI, tests) abre
  conexión transitoria.
- `init_db()` activa `PRAGMA journal_mode=WAL` y `busy_timeout=5000` para
  tolerar clicks rápidos en la app.
- `call_llm()` cae a modo manual si la API falla o no hay key configurada;
  nunca deja la app sin respuesta.
- Los prompts SYS+USER viven por perfil (`profile_prompts`), leídos vía
  `resolve_stage_prompt()` con fallback a `config.json`. `resolve_stage_prompt`
  aplica además `render_profile()` y devuelve el SYS/USER ya sustituido;
  editar un prompt del perfil (directamente en `profile_prompts` o vía
  `/profiles`) cambia el comportamiento de todos sus proyectos.
- Aliases del roadmap (`STAGE_ALIASES` en `app.py`): `scenes_short → scenes`,
  `scripts → script_long`, `thumbnails → thumbnail_long`. Permiten que
  distintos nombres usados por la UI apunten al mismo prompt canónico.
- QC engine: `error` bloquea la transición a `ready`; `warning` e `info` no.
  Coherencia `min_scenes_short = 6` (Fase 2.3): iguala el mínimo exigido
  por el prompt `scenes`.
- Refiner post-QC: `app.build_refiner_prompt(profile, stage_label,
  current_output, issues, original_format)` construye el SYS+USER para
  que el LLM rehaga solo las secciones marcadas por QC. La integración
  con la UI es opcional y todavía no está conectada.
- La carpeta del proyecto en `projects/<safe_name>_<id>/` se sincroniza
  automáticamente con `sync_project_folder()` cada vez que se crea el
  proyecto o se guarda cualquier etapa (research, concept, scripts, scenes,
  metadata, thumbnails, qc). El contrato de archivos es fijo:
  `00_RESUMEN.md`, `01_investigacion.md`, …, `08_paquete_completo.json`.
- El ZIP en `projects/<safe_name>_<id>.zip` es opcional: solo se genera
  bajo demanda desde `POST /projects/<id>/export action=zip`. Borrar un
  proyecto elimina también su carpeta.

## Prompts del pipeline

- Cada prompt SYS arranca con un bloque «Contexto del perfil» que se
  sustituye en runtime: canal, tono, estilo, audiencia, mystery_level,
  drama_level y (en guiones) narration_speed.
- Los prompts visuales (`scenes`, `thumbnail_long`, `thumbnail_short`)
  comparten la constante `config.visual_style.keywords` vía
  `{{app.visual_style_keywords}}`. Editar la lista en CONFIG basta para
  actualizar los tres sin tocar el texto de cada prompt.
- Para añadir una nueva plataforma de metadata: crear la key
  `metadata_<plataforma>` en `config.json` y registrarla en
  `services/parsers.py` (`PLATFORM_PARSERS`,
  `_METADATA_PARSERS_BY_NAME`). No hay grafo: la nueva plataforma
  aparece automáticamente en la página `/projects/<id>/metadata`.
- Para añadir un nodo «refiner» futuro a la UI: usar
  `build_refiner_prompt(...)`, parsear la respuesta con un parser
  específico (pendiente) y guardar el bloque `## OUTPUT REFINADO`
  sobreescribiendo la etapa correspondiente.

## Frontend

- Sin build step. Cambios en `static/` se ven al recargar.
- JS moderno (módulos ES, `fetch`, `URLSearchParams`). No jQuery, no Vue/Svelte.
- Variables CSS del tema (`--bg`, `--accent`, etc.) en `static/style.css`;
  no hardcodear colores en componentes.

## Validación

Antes de cerrar un cambio ejecuta, desde la raíz:

```bash
python test_core.py
python verify_project.py
```

Ambos deben pasar en verde. Si añades rutas, prompts, parsers, una etapa o
una tabla, extiende los tests correspondientes — no los rompas.

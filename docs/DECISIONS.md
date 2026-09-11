# Decisions

Registro de decisiones técnicas relevantes (estilo ADR ligero).

## Formato

```text
## YYYY-MM-DD - Título

Contexto:
Decisión:
Consecuencias:
```

## 2026-08-29 — Aplicación monolítica sin ORM

**Contexto:** El proyecto busca ser una herramienta local simple para
preparar contenido antes de producción. La cantidad de tablas es fija
(10), las consultas son explícitas y el equipo trabaja en Windows con
un único proceso Python.

**Decisión:** Todo en `app.py`, SQLite sin ORM, queries escritas a
mano con `sqlite3.Row` como row factory.

**Consecuencias:**
- Onboarding trivial: leer `app.py` de arriba a abajo.
- Sin migraciones automáticas: cualquier cambio de esquema se aplica
  en `SCHEMA` con `CREATE TABLE IF NOT EXISTS`.
- Migraciones destructivas requieren un script ad-hoc.

## 2026-08-29 — LLM opcional con modo manual por defecto

**Contexto:** No todos los usuarios tienen clave de API ni quieren
pagar por generación. La calidad de los prompts es independiente del
proveedor que los ejecute.

**Decisión:** `call_llm()` admite `manual`, `openai`, `anthropic` y
`custom`. En modo manual devuelve el prompt SYS + USER formateado para
copiar en cualquier LLM externo.

**Consecuencias:**
- Cero costos por defecto.
- Cero dependencias externas (más allá de `requests` o del SDK si se
  instala).
- El usuario controla qué modelo usar y mantiene la conversación en su
  historial.

## 2026-08-29 — Presets para providers OpenAI-compatible

**Contexto:** OpenAI-compatible engloba LM Studio, Ollama, Azure,
servidores custom, etc. Hardcodear los providers en el formulario de
settings era ruidoso y no escalaba.

**Decisión:** Bloque `presets` en `config.json` con `api_key`,
`base_url`, `model`, `type` y `notes`. `active_preset` se resuelve en
cada llamada a `call_llm()` con fallback al bloque legacy `openai`.

**Consecuencias:**
- Añadir un provider nuevo es solo editar `config.json`.
- La UI de presets (`settings.html`) permite crear/editar/activar/
  borrar sin tocar código.
- `active_preset` puede quedar apuntando a un preset borrado: el
  fallback al bloque legacy evita romper el flujo.

## 2026-08-29 — Auto-guardado de prompts por etapa

**Contexto:** El usuario puede generar prompts con un LLM externo y
editarlos a mano. Sin persistencia por proyecto se pierde la
trazabilidad ("¿qué le pedí al LLM para esta investigación?").

**Decisión:** Tabla `stage_prompts` con `UNIQUE(project_id, stage)`
y helper `_ensure_stage_prompt()` que genera y guarda el prompt
canónico automáticamente la primera vez que la etapa tiene contenido.

**Consecuencias:**
- El proyecto conserva los prompts SYS + USER en `06_prompts_usados.md`
  dentro del ZIP exportado.
- `_ensure_stage_prompt` es no destructivo: solo rellena huecos, no
  sobrescribe prompts ya guardados.
- El botón "Regenerar prompts pendientes" de la vista de proyecto
  reaplica `_ensure_stage_prompt` a las siete etapas.

## 2026-08-29 — QC no bloquea por warnings/infos

**Contexto:** El QC detecta errores (falta investigación, guion sin
hook, sin escenas) y avisos (palabra repetida, afirmaciones por
verificar). Bloquear el paso a `status='ready'` por cualquier aviso
era demasiado estricto y desincentivaba usar el QC.

**Decisión:** Solo los `error` bloquean la transición a `ready`. Los
`warning` e `info` se muestran pero no impiden la exportación.

**Consecuencias:**
- El indicador `status='ready'` significa "sin errores bloqueantes",
  no "perfecto".
- El export siempre está disponible, pero `run_qc` debe ejecutarse
  antes para que el ZIP incluya los issues persistidos.

## 2026-08-29 — Export ZIP con un único archivo por sección

**Contexto:** Los pipelines de producción aguas abajo prefieren pocos
archivos grandes bien estructurados antes que muchos pequeños.

**Decisión:** Cada etapa genera un único Markdown:
`04_escenas/escenas.md` contiene todas las escenas con
`**TEXTO AUDIO:**` y `**IMAGEN:**` por escena.

**Consecuencias:**
- Formato `## ESCENA N` inmediato de parsear por herramientas externas.
- `07_paquete_completo.json` mantiene la versión estructurada completa
  para integraciones.

## 2026-08-29 — Eliminar "Prompts visuales" como etapa propia

**Contexto:** La etapa 06 obligaba a rellenar 10 campos JSON por escena
(`subject`, `environment`, `era`, `lighting`, `camera`, `composition`,
`atmosphere`, `style`, `full_prompt_en`, `full_prompt_es`) cuando cada
escena ya almacenaba un `IMAGEN` cinematográfico completo en formato TST.
Para el usuario era trabajo duplicado y conceptual: el IMAGEN de la
escena ya era un prompt utilizable.

**Decisión:** Eliminar la etapa, su ruta, su plantilla y el bloque del
export. El pipeline pasa de 8 a 7 etapas. Las exportaciones se
renumeran (`05_metadata/`, `06_prompts_usados.md`,
`07_paquete_completo.json`). La tabla `prompts` se conserva en el
esquema por compatibilidad pero ya no se referencia.

**Consecuencias:**
- Una etapa menos que mantener; un único sitio para el prompt visual
  por escena.
- El QC ya no exige "coherencia escenas/prompts": ahora exige que cada
  guion tenga al menos sus escenas mínimas.
- Los usuarios que quieran el desglose estructurado (subject,
  environment, etc.) lo extraen del propio IMAGEN.

## 2026-08-29 — Servidor dual Flask/Waitress

**Contexto:** Desarrollo en Windows; necesitamos un modo `--prod`
amigable sin docker ni gunicorn.

**Decisión:** `python app.py` arranca Flask dev (debug + autoreload);
`python app.py --prod` o `TST_SERVER=waitress` arranca Waitress.

**Consecuencias:**
- Sin dependencias extra en dev.
- `waitress` solo se requiere en producción.
- Host/puerto/threads configurables vía `TST_HOST`/`TST_PORT`/`TST_THREADS`.

## 2026-08-29 — Etapa "Miniaturas" con dos paneles

**Contexto:** El canal publica dos versiones por tema (5 min en YouTube,
1 min en Shorts/Reels/TikTok). Cada una necesita una miniatura con su
aspect ratio y composición propias. Hasta ahora no había ningún prompt
para miniaturas: o se improvisaba, o se delegaba en el editor.

**Decisión:** Crear una etapa nueva `thumbnails` entre `metadata` (06)
y `qc` (ahora 08), con dos paneles al estilo de `metadata`. Cada panel
produce un único prompt visual cinematográfico (sin texto overlay, sin
instrucciones de cámara animada) listo para Midjourney / Flux / DALL-E.
Se añade la tabla `thumbnail_records` (`UNIQUE(project_id, script_type)`)
y el parser `parse_thumbnail` dedicado al bloque `## MINIATURA`.

**Convenciones heredadas:**
- Las dos plantillas (`thumbnail_long`, `thumbnail_short`) comparten las
  mismas keywords de estilo que el system prompt de `scenes`
  (`Cinematic Hyperrealism`, `Orange & Teal`, `Volumetric Lighting`, …)
  más un sufijo específico del aspect ratio (`16:9 Aspect Ratio`,
  `Thumbnail Composition`, … o `9:16 Aspect Ratio`, `Centered Subject`).
- La etapa se considera completa solo cuando hay registros para ambos
  `script_type` (long + short). Un solo registro deja la etapa
  pendiente para que el editor recuerde generar la otra miniatura.
- Renumeración del ZIP: `06_thumbnails/`, `07_prompts_usados.md`,
  `08_paquete_completo.json`. Es la tercera renumeración del export
  pero la tabla `prompts` se mantiene vacía por compatibilidad.

**Consecuencias:**
- Una nueva etapa que mantener, pero el patrón es 1:1 con `metadata`:
  dos plantillas en config.json, dos builders, una sola ruta, una sola
  página con dos macros.
- El bundle JSON incluye ahora la clave `thumbnails` con la lista de
  registros.
- `verify_fosiles.py` y `test_core.py` ganan asserts específicos para
  miniaturas; sin ellos un fallo en la nueva etapa pasaría inadvertido.

## 2026-09-01 — Prompts por perfil (no por proyecto)

**Contexto:** La tabla `stage_prompts` almacenaba los prompts SYS + USER
editados por proyecto. Eso obligaba al usuario a reescribir el prompt
en cada nuevo proyecto aunque quisiera la misma voz editorial. Además,
los prompts guardados se editaban desde seis plantillas distintas
(`research.html`, `concept.html`, `scripts.html`, `scenes.html`,
`metadata.html`, `thumbnails.html`), sin una visión unificada.

**Decisión:** Migrar la persistencia a una tabla `profile_prompts`
con `UNIQUE(profile_id, stage)`. La migración se ejecuta una sola vez
en `init_db()` (controlada por `_schema_migrations`) y copia los
prompts de `stage_prompts` al perfil de cada proyecto antes de dropear
la tabla legacy. `resolve_stage_prompt(profile_id, stage)` es la única
forma de leer un prompt: busca en `profile_prompts` y, si no existe,
devuelve `CONFIG['prompts'][stage]['system'/'format']`. Esto unifica
default + override en un único punto y permite que los proyectos que
compartan perfil compartan también los prompts.

**Consecuencias:**
- Cambiar un prompt en un perfil lo cambia para todos los proyectos que
  lo usan. Era el comportamiento esperado por el usuario desde la
  versión 1.x; se hace explícito.
- Las páginas de cada etapa dejan de mostrar el bloque «Guardar
  prompt»: la edición ahora vive en `/profiles/<id>/graph`.
- `07_prompts_usados.md` se regenera desde el perfil en el export,
  no desde el proyecto.
- La ruta `backfill_stage_prompts` desaparece: el grafo es la única
  fuente de prompts editados.

## 2026-09-01 — Editor visual de grafo por perfil

**Contexto:** El usuario pidió una vista estilo n8n donde pudiera
modificar todos los prompts de un perfil, añadir pasos custom y
ejecutar el flujo nodo a nodo sobre un proyecto. Las seis
plantillas existentes eran un buen sitio para editar un prompt
pero daban una visión fragmentada y obligaban a saltar de página en
página para revisar el conjunto.

**Decisión:** Añadir dos páginas nuevas:

- `/profiles/<id>/graph` — Editor: React Flow v12 cargado por
  importmap desde `esm.sh` (sin build step, sin dependencias NPM,
  único módulo ESM en `static/graph.js`). Nueve nodos fijos
  pre-creados en posiciones iniciales (grid 3×3) más la opción de
  añadir nodos custom con su propio SYS + USER y conexiones libres.
  Las posiciones se persisten con debounce de 600 ms.
- `/projects/<id>/run` — Runner: mismo grafo, con el flujo de
  ejecución. `POST /run/execute` despacha a los builders/parsers
  existentes para los nodos fijos (misma ruta de generación y
  persistencia que la página clásica) y hace `call_llm` directo
  para los custom, interpolando `{{ inputs.<key> }}` con los
  outputs previos. Cada ejecución se persiste en `node_executions`
  con su estado (`idle/running/ok/error`) y duración.

**Consecuencias:**
- El editor visual es ahora la única vía para editar prompts del
  perfil. Las plantillas de etapa siguen mostrando el prompt
  generado al vuelo, pero no persisten (la persistencia la hace el
  grafo).
- Los nodos custom son texto libre: el LLM recibe los prompts SYS +
  USER tal cual y se guarda el output crudo en `node_executions`. Si
  el proyecto necesita reutilizar ese output, basta con encadenarlo
  vía `inputs: ["otro_nodo"]`.
- React Flow se carga por importmap desde `esm.sh` (≈ 700 kB total
  con React + ReactDOM). El navegador hace una sola petición y, una
  vez cacheada, las recargas son instantáneas. Si en el futuro
  hace falta trabajar offline, hay que sustituir el importmap por
  bundles locales en `static/vendor/`.
- `test_core.py` cubre `resolve_stage_prompt`, la migración
  `stage_prompts → profile_prompts`, y la rama custom del ejecutor;
  `verify_fosiles.py` sigue cubriendo el flujo end-to-end clásico,
  que no cambia.

## 2026-09-01 — Extracción de services/ y blueprints/ como PoC

**Contexto:** El monolito deliberado (ADR-001) había crecido hasta
3 500 líneas y la auditoría 2026-09-01 identificó que mezclaba
varias responsabilidades (rutas HTTP, parsers, llamadas LLM, reglas
QC, prompts builders, persistencia). El monolito sigue siendo válido
como filosofía de proyecto pero dos áreas estaban claramente
aisladas del resto: el editor de grafo (`/profiles/<id>/graph/*`) y
el runner (`/projects/<id>/run/*`), candidatos naturales a blueprint.
También había lógica no-HTTP (parsers puros, `call_llm`, `run_qc`)
que vivía entre las rutas y dificultaba los tests aislados.

**Decisión:** Hacer una **PoC** que valida dos extracciones
mínimas e independientes:

1. `services/` para funciones puras / no-HTTP:
   - `services/parsers.py` — 9 parsers + `count_words`,
     `estimate_duration_seconds`. Sin dependencias de Flask, CONFIG
     ni DB.
   - `services/llm.py` — `call_llm`, `_manual_fallback`,
     `llm_output_is_manual`. Lee `CONFIG` con local import.
   - `services/qc.py` — `run_qc`, `save_qc_issues`. Lee `get_db`,
     `CONFIG["qc"]["checks"]`, `format_timecode`, `now_iso` con
     local import.

2. `blueprints/` para dominios aislados:
   - `blueprints/graph.py` — `graph_bp` con las 4 rutas del editor.
   - `blueprints/runner.py` — `runner_bp` con las 3 rutas del
     runner. Cada blueprint usa local import dentro de los handlers
     para romper el ciclo con `app.py`.

`app.py` re-exporta los símbolos extraídos para preservar la API
existente (`from app import parse_research` sigue funcionando, lo
que evita tocar `test_core.py` ni `verify_project.py`).

**Consecuencias:**
- `app.py` pasa de 3 500 a 2 477 líneas (-29%).
- La separación `services/` vs `blueprints/` deja clara la frontera
  entre lógica reutilizable (sin Flask) y capa HTTP.
- Los local imports rompen los ciclos a costa de un coste mínimo
  en tiempo de import por request (resoluble con caché si hace
  falta, no es problema hoy).
- Las plantillas que recibían `graph_data.saveUrl`/etc. no cambian
  porque los blueprints siguen emitiendo las mismas URLs vía
  `url_for(...)` con prefijo del blueprint.

**Reversibilidad (qué se撤収 si la PoC no convence):**
- `git revert` de los commits de T2.1 y T2.2.
- El monolito sigue funcionando idéntico porque `app.py`
  re-exporta los símbolos. Solo cambia la estructura de carpetas.
- Si la fricción (local imports, navegación entre archivos,
  doble fuente de verdad) supera el beneficio, ADR-001 sigue
  vigente y se documenta aquí que "monolito confirmado para este
  proyecto".

## 2026-09-05 — Nodo fijo `scenes_short` y limpieza del UI de prompts

**Contexto:** Tras la auditoría del proyecto el 2026-09-05 se
detectaron dos issues residuales del sprint 2026-09: (1) las páginas
por etapa (research, concept, scripts, scenes, metadata, thumbnails)
emitían un form con `action=save_prompt` que ningún handler en
`app.py` procesaba desde la eliminación de la persistencia por
proyecto en favor de los prompts por perfil; (2) el runner de grafo
sólo cubría escenas del guion largo (`scenes`) pero la etapa Escenas
del QC exige ambos guiones, dejando al guion corto sin atajo desde
el runner.

**Decisión:**
- Sustituir el form roto por un enlace "Editar en el grafo" que
  apunta a `/profiles/<id>/graph` desde `_macros.html:prompt_editor`
  y refactorizar los forms inline de `scripts.html`, `metadata.html`
  y `thumbnails.html` para usar la macro. Las textareas pasan a
  `readonly` para evitar ediciones accidentales que se perderían.
- Añadir `scenes_short` como 10º nodo fijo del grafo (paralelo a
  `scenes`), con su builder, posición default y arista
  `script_short → scenes_short`. La lógica de persistencia se extrae
  a un helper `_persist_scenes(conn, project_id, script_type, ...)`
  reutilizado por ambos. `resolve_stage_prompt` añade el alias
  `scenes_short → scenes` para reusar los prompts SYS/USER del guion
  largo (mismo contrato, distinto target de persistencia).

**Consecuencias:**
- El editor de grafo pasa de 9 a 10 nodos fijos. La afirmación
  "nueve etapas fijas" en `docs/ARCHITECTURE.md` se actualiza.
- `_persist_scenes` queda listo para nuevos tipos de guion (no
  rompe el contrato actual).
- Los tests `test_get_or_create_fixed_graph_nodes` se actualiza de
  9 a 10 filas esperadas.
- La asimetría páginas-clásicas vs. runner se cierra: las páginas
  `/scenes` ya soportaban guion corto; ahora el runner también.
- Tests E2E del runner vía `test_client()` cierran la tarea
  pendiente del sprint 2026-09: cubren el ciclo `idle → running → ok`
  en `node_executions` para los 10 nodos fijos.

**Reversibilidad:**
- `git revert` de los commits asociados restaura los 9 nodos y el
  form inline roto (que volvería a fallar como antes, sin regresión
  funcional).

## 2026-09-07 — Modo manual exclusivo (v2.0)

**Contexto:** Tras 1.0 la herramienta soportaba cuatro proveedores
LLM (manual, openai, anthropic, custom) con presets editables desde
`/settings`. La auditoría 2026-09-07 confirmó que ningún usuario
activo consumía la API: el modo manual cubre todos los flujos
(producto verificado en `verify_project.py` y `examples/`) y los
presets se habían quedado desfasados (URLs placeholder, modelos
cambiados por los proveedores). Mantener el cableado HTTP de tres
proveedores + `urllib.request` + parser de presets + página de
configuración era coste de mantenimiento sin usuario. Además, los
ADRs previos (2026-08-29 "LLM opcional con modo manual por defecto",
2026-08-29 "Presets para providers OpenAI-compatible") declaraban
que el modo manual era el camino feliz; esta decisión lo hace
explícito eliminando la otra rama.

**Decisión:** Eliminar la integración con OpenAI, Anthropic y los
presets personalizados. La herramienta es solo modo manual desde
2.0.0:

- `services/llm.py` se renombra a `services/manual.py` y conserva
  solo `call_llm` (que ahora es trivial: devuelve el bloque
  `## [MODO MANUAL]`), `llm_output_is_manual` y `_manual_fallback`
  (helper privado, ya no representa un fallback de error).
- `app.py` pierde `llm_mode()` y `PROVIDER_NAMES`; el contexto de
  plantilla expone una constante `LLM_MODE` con el modo manual
  único. Los logs de arranque pasan de "LLM provider: manual" a
  "Modo: manual".
- `blueprints/settings.py`, `templates/settings.html` y la pestaña
  "Configuración" del nav desaparecen. La página `/settings`
  devuelve 404.
- `config.json` pierde el bloque `llm` entero (provider, openai,
  anthropic, active_preset, presets, temperature, max_tokens).
- Las 6 plantillas por etapa eliminan la rama
  `{% elif llm.key == 'manual' %}` (siempre verdadera) y el botón
  queda como `{% if saved %}Regenerar prompt{% else %}Generar prompt{% endif %}`.
- `test_core.py` pierde los 4 toggles
  `app.CONFIG["llm"]["provider"] = "manual"` — el modo manual es el
  único modo, no hace falta forzar nada.

**Consecuencias:**

- Quien venía usando la API debe copiar los prompts manualmente a
  su LLM. El contrato del output (secciones `## RESUMEN`,
  `## ÁNGULO`, `## HOOK`, `## CONTEXTO`, etc.) no cambia: cualquier
  LLM moderno lo entiende.
- `requirements.txt` no cambia: `urllib.request` es stdlib y nunca
  fue dependencia de runtime; `anthropic` SDK nunca estuvo
  pinneado (era opcional).
- Cero secretos en `.env` ni `config.json` que retirar por parte
  del proyecto (los campos `api_key` están vacíos desde 1.0). Si
  el usuario tenía claves reales, debe retirarlas manualmente.
- `app.py` baja ~70 líneas: `llm_mode()` (30 líneas),
  `PROVIDER_NAMES` (6), import de `blueprints.settings`,
  `register_blueprint(settings_bp)`, log de provider en arranque.
- Bump de versión mayor (SemVer 1.x → 2.x) por cambio incompatible.

**Reversibilidad:**

- `git revert` del commit 2 (`feat!: quitar proveedores LLM`)
  restaura:
  - `services/llm.py` con todas las ramas API (hay que
    `git mv services/manual.py services/llm.py` antes).
  - `blueprints/settings.py` y `templates/settings.html` desde el
    commit anterior.
  - Las llamadas a `url_for('settings.view')` en `templates/base.html`.
  - Las ramas `{% elif llm.key == 'manual' %}` en las 6 plantillas.
  - Los 4 toggles `app.CONFIG["llm"]["provider"]` en `test_core.py`.
  - El bloque `llm` de `config.json` (hay que reescribirlo con los
    valores del commit anterior).
- El commit 1 (`chore(audit): aplicar limpieza de hallazgos H1-H9`)
  es independiente y se mantiene: sus cambios (borrar duplicados,
  limpiar F401, etc.) son útiles incluso con la rama API restaurada.
- Tras el revert, sería seguro bumpear a `2.0.1` y publicar el
  revert; o bien quedarse en `2.0.0` y abrir un nuevo sprint que
  reintroduzca los proveedores con mejor diseño (SDK oficial por
  proveedor, OAuth en vez de API keys, etc.).

## 2026-09-10 — Auditoría de prompts del pipeline (T3)

**Contexto:** La release v2.0.0 mantenía los prompts SYS por etapa como
texto plano sin inyección de variables, con keys huérfanas en
`config.json` (`metadata_youtube`, `metadata_shorts`) y un bug latente
en `_roadmap_instruction_for` que hacía que las ediciones de prompts
per-video en `profile_prompts` nunca llegaran al runtime (siempre se
usaba el fallback de CONFIG).

**Decisión:** Auditoría en cuatro frentes, en orden:

1. **Housekeeping** — Borrar `metadata_youtube` y `metadata_shorts` de
   `config.json`. Refactor `KNOWN_FIXED_NODE_KEYS`,
   `DEFAULT_NODE_LABELS`, `DEFAULT_NODE_POSITIONS` y `DEFAULT_EDGES`
   para usar los nombres modernos (`metadata_youtube_long`,
   `metadata_youtube_short`, `metadata_facebook_long`,
   `metadata_reels_short`). Eliminar el dict legacy en
   `build_metadata_prompt`. Refactor del canonical map en
   `_persist_fixed_result` y de `_build_user_msg_for_fixed` en el
   runner del grafo.

2. **Aliases en `resolve_stage_prompt`** — Nuevo dict
   `STAGE_ALIASES = {"scenes_short": "scenes", "scripts":
   "script_long", "thumbnails": "thumbnail_long"}`. Arreglo del bug en
   `_roadmap_instruction_for`: ahora prueba primero la key del roadmap
   (como se guardan en `profile_prompts`) antes que las alternativas
   declaradas en `ROADMAP_PROMPT_KEYS`.

3. **Mini-motor de plantillas `{{var}}`** — Nuevo módulo
   `services/templates.py` con `render(text, context)` y
   `render_profile(text, profile)`. Soporta paths con punto
   (`{{profile.mystery_level}}`); paths desconocidos se sustituyen por
   cadena vacía y se registran en un `RenderReport.unknown`. Aplicado
   dentro de `resolve_stage_prompt` y dentro de `app_context()` (que
   expone `app.visual_style_keywords` desde la constante `visual_style`
   en CONFIG). Cada prompt SYS ahora arranca con un bloque
   «Contexto del perfil» que se sustituye en runtime.

4. **Estrategia editorial** — `concept` exige anclaje en hechos
   confirmados y declara explícitamente las afirmaciones sin verificar
   que NO debe usar como base. `build_concept_prompt` ahora inyecta
   los bloques `facts`, `theories`, `sources` y `unverified` del
   `parse_research`. `scenes` declara arco emocional progresivo
   (asombro → misterio → pregunta → escala). `min_scenes_short`
   sube de 4 → 6 para alinearse con la regla «mínimo 6 escenas» del
   prompt. `parse_metadata` se refactoriza a dispatcher por
   plataforma con cuatro ramas (`youtube_long`, `youtube_short`,
   `facebook_long`, `reels_short`) que siempre devuelven el dict
   canónico completo.

5. **DRY keywords visuales** — Las 14 keywords cinematográficas
   repetidas en `scenes`, `thumbnail_long`, `thumbnail_short` se
   extraen a `CONFIG.visual_style.keywords`. Los prompts visuales
   ahora referencian `{{app.visual_style_keywords}}` en lugar de la
   lista literal.

6. **Refiner post-QC** — Nueva key `prompts.refiner` con un prompt
   que toma (output actual + issues QC + FORMAT original de la etapa)
   y devuelve la respuesta refinada solo donde hace falta. Builder
   `build_refiner_prompt(profile, stage_label, current_output, issues,
   original_format)`. La integración con la UI es optativa (no
   implementada en esta tanda).

**Consecuencias:**

- `resolve_stage_prompt` ya no es solo «leer de DB o CONFIG»: ahora
  también renderiza con el perfil activo. Las ediciones del usuario en
  `/profiles/<id>/graph` surten efecto aunque vivan bajo el key del
  roadmap (`scripts`, `metadata`, `thumbnails`).
- Si un perfil futuro cambia `mystery_level` o `tone` los prompts
  SYS se adaptan sin reescribirlos: el motor de plantillas unifica la
  voz editorial.
- `parse_metadata` se rompe por plataforma, no por prompt: cada rama
  valida solo los campos que su prompt declara. Los campos no
  rellenados quedan vacíos pero presentes en el dict canónico.
- `verify_project.py` y `test_core.py` crecen ~12 tests nuevos. El
  total pasa en verde.
- Backup de `workflow.db` y `config.json` previos en `backups/`.

## 2026-09-11 — Purga del editor de grafo y del runner (v2.1.0)

**Contexto:** La auditoría arquitectónica 2026-09-11 descubrió que los
blueprints `blueprints/graph.py` (`graph_bp`) y `blueprints/runner.py`
(`runner_bp`) — extraídos en T2.2 (ADR 2026-09-01) y descritos como
features activas en `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`,
`docs/DECISIONS.md`, `CHANGELOG.md`, `TASKS.md` y `PRODUCT.md` —
**no se registraban en `app.py:94`**. El comentario explícito en
`app.py:4261-4265` lo declaraba, pero el resto de la documentación
seguía presentándolas como rutas accesibles al usuario.

El monolito arrastraba ~830 líneas de código muerto: el CRUD de
`profile_graph_nodes` y `node_executions` (incluidos `KNOWN_FIXED_NODE_KEYS`,
`DEFAULT_NODE_LABELS`, `DEFAULT_NODE_POSITIONS`, `DEFAULT_EDGES`,
`get_or_create_fixed_graph_nodes`, `fetch_graph_nodes`,
`fetch_graph_edges_as_eedges`, `save_graph_node`, `delete_graph_node`,
`update_graph_layout`, `_interpolate_inputs`, `_truncate_to_bytes`,
`_persist_scenes`, `_persist_fixed_result`, `_load_first_script`,
`_build_user_msg_for_fixed`, `execute_graph_node`), dos templates
huérfanas (`profile_graph.html`, `project_run.html`) y cuatro módulos
ESM en `static/graph/` (~34 KB). `init_db()` ya ejecutaba
`DROP TABLE IF EXISTS profile_graph_nodes / node_executions` en cada
arranque porque las tablas nunca se creaban, lo que confirmaba que el
código CRUD siempre operaba sobre tablas vacías.

El parámetro `graph_url` de `_macros.html:prompt_editor` nunca se
asignaba en el contexto del template, así que el botón "Editar en el
grafo" estaba siempre oculto. `STAGE_ALIASES` se conserva (lo usa
`resolve_stage_prompt` para resolver nombres ambiguos del roadmap
a prompts canónicos).

**Decisión:** Eliminar todo el código muerto del monolito y alinear
docs con el estado real de la build. Mantener la dirección tomada
en v2.0 (modo manual exclusivo, monolito con `services/` y
`blueprints/`) sin reintroducir el editor de grafo ni el runner.

Alcance del borrado:

- Blueprints: `blueprints/graph.py`, `blueprints/runner.py`.
- Templates: `templates/profile_graph.html`, `templates/project_run.html`.
- Estáticos: `static/graph.js`, `static/graph/` (cuatro módulos ESM).
- `app.py`: ~830 líneas del CRUD de grafo + ejecutor + helpers
  (`_persist_scenes`, `_persist_fixed_result`, `_load_first_script`,
  `_build_user_msg_for_fixed`, `_truncate_to_bytes`, etc.). El
  monolito pasa de 4 339 a 3 502 líneas (-19 %), más cerca del
  tamaño declarado por el ADR-010 (2 477 líneas tras T2.2).
- `_macros.html:prompt_editor`: parámetro `graph_url` eliminado.
  Seis call-sites limpios (`concept`, `metadata`, `scenes`,
  `thumbnails`, `research`, `scripts`).
- `init_db()` y `_migrate_to_roadmap_model`: las dos
  `DROP TABLE IF EXISTS` para `profile_graph_nodes` /
  `node_executions` se mantienen en `init_db()` por compatibilidad
  con BDs legacy que aún tengan restos. El SCHEMA no las crea.
- `services/templates.py`, `services/parsers.py`, `services/qc.py`,
  `services/sync.py`, `services/stages.py`, `services/manual.py`
  intactos: el editor de grafo no los tocaba.
- `blueprints/profiles.py` intacto: era el único blueprint
  registrado y sigue cubriendo las rutas `/profiles`.
- Documentación alineada: `README.md` pierde la sección "Editor
  visual de grafo (por perfil)"; `AGENTS.md` reescribe las
  descripciones de `blueprints/` y `static/`; `docs/ARCHITECTURE.md`
  reescrito (tabla de servicios, blueprints activos, modelo de
  datos sin `profile_graph_nodes` ni `node_executions`); este ADR
  cierra el ciclo. `CHANGELOG.md` publica la release `2.1.0`.
- Linter limpio: `ruff check` baja de 14 errores históricos a 0
  (10 auto-fix vía `ruff check --fix`, 4 manuales: 1 `F401`, 3 `F841`).

**Consecuencias:**

- Si en el futuro alguien quiere reactivar el editor de grafo o el
  runner, lo hará desde cero: el código está fuera del árbol, no
  en un feature flag. La reintroducción requerirá reintroducir las
  tablas `profile_graph_nodes` y `node_executions`, el SCHEMA, las
  migraciones, los blueprints, los templates, el JS y los tests E2E.
- La documentación vuelve a ser una fuente única de verdad: lo que
  dice el `README` existe en la build. El próximo onboarding ya no
  se va a topar con la inconsistencia.
- Bump menor (SemVer 2.0.x → 2.1.0) por cambio no-rompedible: la API
  pública del usuario no cambia, solo se elimina código inaccesible.

**Reversibilidad:**

- `git revert` del commit de purga restaura el código en su forma
  previa al audit. Las tablas se recrean implícitamente la próxima
  vez que se ejecute `init_db()` si el SCHEMA las incluye (no las
  incluye hoy), pero los blueprints huérfanos vuelven a fallar al
  no estar registrados — exactamente la misma situación pre-purga.
- Si la reintroducción se aborda como nuevo sprint, partir del ADR
  original (`## 2026-09-01 — Editor visual de grafo por perfil`)
  y rehacer las decisiones obsoletas (React Flow por importmap →
  bundle local, alias del runner, etc.) en un ADR propio.

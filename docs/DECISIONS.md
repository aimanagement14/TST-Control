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

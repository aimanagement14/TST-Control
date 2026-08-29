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
- El proyecto conserva los prompts SYS + USER en `07_prompts_usados.md`
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
`04_escenas/escenas.md` contiene todas las escenas y
`05_prompts/prompts.md` todos los prompts EN + ES.

**Consecuencias:**
- Formato `## ESCENA N` con `**TEXTO AUDIO:**` y `**IMAGEN:**`
  inmediato de parsear por herramientas externas.
- `08_paquete_completo.json` mantiene la versión estructurada completa
  para integraciones.

## 2026-08-29 — Servidor dual Flask/Waitress

**Contexto:** Desarrollo en Windows; necesitamos un modo `--prod`
amigable sin docker ni gunicorn.

**Decisión:** `python app.py` arranca Flask dev (debug + autoreload);
`python app.py --prod` o `TST_SERVER=waitress` arranca Waitress.

**Consecuencias:**
- Sin dependencias extra en dev.
- `waitress` solo se requiere en producción.
- Host/puerto/threads configurables vía `TST_HOST`/`TST_PORT`/`TST_THREADS`.

# AGENTS

Guía para agentes de IA que trabajan en este proyecto.

## Convenciones

- Stack: **Python 3.14 + Flask 3 + Jinja2 + SQLite** (sin ORM), frontend sin build
  step (`static/app.js`, `static/graph.js`, importmap a `esm.sh`).
- Type hints donde aporten valor. Evitar `Any` salvo en bordes justificados
  (parsing LLM, JSON externo).
- Funciones pequeñas y con responsabilidad única. Un módulo = una responsabilidad.
- Sin dependencias nuevas sin motivo: `requirements.txt` cubre Flask + waitress.
- Documentar solo cuando aporte valor: nada de docstrings vacíos ni comentarios
  redundantes.
- UI y copy en español por defecto (configurable por preset LLM).

## Estructura

- `app.py` — monolito deliberado: rutas + servicios de dominio + parsers + QC.
  Las funciones puras de parsing/QC viven a nivel de módulo y se cubren con
  `test_core.py`.
- `templates/` — Jinja2. `_macros.html`, `_rail.html`, `_stepper.html` para
  piezas reutilizables; el resto son páginas por etapa.
- `static/` — JS/CSS sin bundler. `app.js` para chrome general, `graph.js`
  para el editor de grafo (React Flow v12 por importmap).
- `config.json` — única fuente para prompts SYS/USER, presets LLM, umbrales
  QC y tema visual. No se mueve a YAML/ENV sin motivo.
- `workflow.db` — SQLite. Migraciones controladas por `_schema_migrations`
  (idempotentes).
- `test_core.py` — parsers, QC, utilidades, prompts por perfil, CRUD de grafo.
- `verify_project.py` — verificación end-to-end con datos simulados de LLM
  (`PROJECT_ID = 2`, crea proyecto sintético si no existe).
- `docs/ARCHITECTURE.md` y `docs/DECISIONS.md` — las decisiones técnicas y
  de arquitectura viven ahí, no en comentarios sueltos.

## Backend

- `get_db()` cachea la conexión en `flask.g` durante el ciclo de petición;
  `close_db` (teardown) la cierra. Fuera de contexto (CLI, tests) abre
  conexión transitoria.
- `init_db()` activa `PRAGMA journal_mode=WAL` y `busy_timeout=5000` para
  tolerar clicks rápidos en el runner del grafo.
- `call_llm()` cae a modo manual si la API falla o no hay key configurada;
  nunca deja la app sin respuesta.
- Los prompts SYS+USER viven por perfil (`profile_prompts`), leídos vía
  `resolve_stage_prompt()` con fallback a `config.json`. Editar un prompt en
  el editor de grafo del perfil cambia el comportamiento de todos sus
  proyectos.
- QC engine: `error` bloquea la transición a `ready`; `warning` e `info` no.
- La carpeta del proyecto en `projects/<safe_name>_<id>/` se sincroniza
  automáticamente con `sync_project_folder()` cada vez que se crea el
  proyecto o se guarda cualquier etapa (research, concept, scripts, scenes,
  metadata, thumbnails, qc). El contrato de archivos es fijo:
  `00_RESUMEN.md`, `01_investigacion.md`, …, `08_paquete_completo.json`.
- El ZIP en `projects/<safe_name>_<id>.zip` es opcional: solo se genera
  bajo demanda desde `POST /projects/<id>/export action=zip`. Borrar un
  proyecto elimina también su carpeta.

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

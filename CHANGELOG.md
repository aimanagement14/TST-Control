# Changelog

Todos los cambios relevantes de Todo Sobre Todo se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
el versionado [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Fixed

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

### Changed

- `test_core.py` añadía `gc.collect()` entre tests QC/export para
  evitar `PermissionError` en la limpieza de `tempfile.TemporaryDirectory`
  en Windows (SQLite conserva el handle del `.db` aunque el `with`
  cierre la conexión).
- Documentación: `docs/ARCHITECTURE.md` y `docs/DECISIONS.md` pasan de
  plantilla vacía a una descripción completa de módulos, modelo de
  datos y decisiones técnicas.
- `TASKS.md` actualizado con el backlog real.

## [1.0.0] - 2026-08-29

### Added

- Importación inicial de Todo Sobre Todo, centro local de planificación
  de contenido audiovisual (Flask + Jinja2 + SQLite).
- Aplicación monolítica `app.py` con flujo TEMA → INVESTIGACIÓN → CONCEPTO →
  GUION → ESCENAS → PROMPTS → METADATA → CONTROL DE CALIDAD → EXPORTAR.
- Modos manual y API multi-proveedor (OpenAI, Anthropic, Azure, Ollama,
  LM Studio y presets personalizables vía `config.json`).
- Verificador CLI de calidad (`verify_fosiles.py`) y suite de tests
  (`test_core.py`).
- Perfiles reutilizables de contenido (tipo, audiencia, tono, misterio,
  drama, velocidad, plataformas).
- Exportación de cada proyecto como ZIP con `00_RESUMEN.md`,
  `01_investigacion.md`, guiones, escenas, prompts, metadata y JSON
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
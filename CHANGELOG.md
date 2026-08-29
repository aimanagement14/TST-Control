# Changelog

Todos los cambios relevantes de Todo Sobre Todo se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
el versionado [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

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
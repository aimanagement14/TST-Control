# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Single user: el propio creador del canal **Todo Sobre Todo**. Trabaja en local en Windows, lanza la herramienta con `python app.py` y opera todo el flujo de preproducción él mismo. La herramienta no se entrega a terceros en esta fase.

## Product Purpose

Centro de control de preproducción para el canal de documentales de misterio / temáticas alternativas Todo Sobre Todo. Cubre todo el ciclo desde un tema hasta un paquete ZIP listo para entregar al pipeline de producción audiovisual (imagen, voz, edición), sin salir a herramientas externas.

Éxito = que cada tema termine en un ZIP exportado, completo y consistente, listo para pasar a producción sin retrabajo.

## Positioning

Lo que un vecino no podría copiar honestamente: **un pipeline completo de preproducción que corre entero en local, en un único proceso Python, sin nube, sin cuentas y sin costes por uso** — desde el tema hasta el ZIP entregable al pipeline de producción. Los prompts SYS por etapa, calibrados para el nicho misterio / alternativo, son el activo editorial.

## Operating Context

- Flujo de un solo autor en Windows: una persona, una máquina, un proceso Flask local (`http://localhost:5000`).
- Modo LLM manual por defecto: la herramienta genera los prompts SYS + USER estructurados; el usuario los pega en ChatGPT / Claude / Gemini y devuelve la respuesta, que se parsea automáticamente. Sin clave de API, sin coste, sin telemetría.
- Modo LLM API opcional: cualquier endpoint OpenAI-compatible (MiniMax text API, Azure OpenAI, Ollama local, LM Studio, servidor custom) configurable por presets.
- Cada proyecto recorre las 8 etapas del pipeline; los prompts viven a nivel de **perfil**, no de proyecto, y se editan vía el blueprint `/profiles` (sin build step).
- Cada tema produce **dos formatos de vídeo**: documental 5 min (YouTube) + corto 1 min (Shorts / Reels / TikTok), cada uno con su guion, metadata y miniatura.
- La unidad de entrega al pipeline aguas abajo es el **ZIP exportado** (`projects/<nombre>.zip`), con un Markdown por sección + `paquete_completo.json`.

## Capabilities and Constraints

- Pipeline de 8 etapas: investigación → concepto → guiones (5 min + 1 min) → escenas → metadata → miniaturas → control de calidad → exportar.
- Prompts SYS + USER persistidos por perfil (`profile_prompts`), leídos vía `resolve_stage_prompt()` con fallback a `config.json`.
- Perfiles configurables: `content_type`, `audience`, `tone`, `style`, `mystery_level`, `drama_level`, `narration_speed`, `platforms`.
- QC engine: bloquea solo por errores; warnings e infos no impiden la exportación. Cubre conteo de palabras, duraciones objetivo, hook / CTA / estructura, repeticiones, mínimo de escenas, mínimo de fuentes, afirmaciones sin verificar.
- Stack deliberadamente simple: un solo `app.py`, SQLite vía `sqlite3` (sin ORM), Jinja2, sin bundler JS.
- Migraciones de esquema controladas por `_schema_migrations` (idempotentes).
- Sin nube, sin cuentas, sin telemetría; el único outbound runtime es la llamada al LLM cuando el modo API está activo.
- Decisión pendiente: si el próximo trabajo visual es **refinamiento** del tema oscuro cinematográfico actual o un **mundo nuevo** que lo reemplace. PRODUCT.md solo registra verdad de producto, no decide eso.

## Brand Commitments

- Nombre y tagline vinculantes: **Todo Sobre Todo** / *Centro de producción de contenido*.
- Voz editorial: serio con toques intrigantes, narrativo; nicho misterio y temáticas alternativas.
- Identidad visual: **tema oscuro cinematográfico actual es vinculante**. Paleta anclada en `#0a0a0a` (fondo) y `#d4af37` (acento dorado); los prompts de escenas y miniaturas aplican grading cinematográfico Orange & Teal con `Cinematic Hyperrealism`, `Volumetric Lighting`, `Atmospheric Fog`, `Filmic Lighting`, `Epic Scale` como contrato visual.
- Perfil por defecto `Todo Sobre Todo / Misterio` preconfigurado (mystery_level 7, drama_level 6, 150 wpm, estilo cinematográfico, contrastado, con toques conspiranoicos).
- Sin tipografía ni logos de terceros impuestos más allá de los que ya viven en `static/style.css`.

## Evidence on Hand

- Prompts SYS reales calibrados al nicho viven en `config.json → prompts.*.system` / `prompts.*.format`.
- Perfiles con mystery_level, drama_level, platforms, narration_speed viven en `workflow.db`.
- Producciones reales que pasan por la herramienta y se exportan como ZIPs en `projects/`.
- Estructura del ZIP exportado (`00_RESUMEN.md`, `01_investigacion.md`, `02_concepto.md`, `03_guiones/`, `04_escenas/escenas.md`, `05_metadata/`, `06_thumbnails/`, `07_prompts_usados.md`, `08_paquete_completo.json`) es el contrato con el pipeline de producción aguas abajo.
- Decisiones técnicas registradas en `docs/DECISIONS.md` y arquitectura en `docs/ARCHITECTURE.md`.

## Product Principles

1. **Local first**: corre en una sola máquina, en un solo proceso Python, sin nube ni cuentas.
2. **LLM-agnóstico**: funciona con cualquier LLM externo vía copy/paste; el modo API es un acelerador opcional, nunca un requisito.
3. **Una sola fuente de verdad para prompts**: los prompts viven por perfil; editar en un sitio cambia el comportamiento de todos los proyectos de ese perfil.
4. **Un paquete por vídeo, listo para entregar**: el ZIP exportado es la unidad de handoff al pipeline de producción.
5. **Sin duplicación silenciosa**: cada dato se introduce una vez; las etapas aguas abajo lo consumen, no lo reescriben.

## Accessibility & Inclusion

- Herramienta local de un solo autor en Windows; sin audiencia pública, sin requisito WCAG establecido.
- UI en español por defecto.

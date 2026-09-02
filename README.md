# Todo Sobre Todo — Centro de producción de contenido

Herramienta local para **planear, investigar y preparar todo el contenido**
antes de pasar a producción audiovisual.

No genera imágenes, videos ni audio. Solo planifica y prepara.

## Arquitectura (deliberadamente simple)

```
TodoSobreTodo/
├── app.py            # toda la lógica
├── config.json       # configuración, perfiles, plantillas de prompts
├── workflow.db       # base de datos SQLite (se crea al arrancar)
├── templates/        # HTML Jinja2
├── static/           # CSS y JS de interfaz
├── projects/         # exportaciones
└── requirements.txt
```

Sin ORM, sin microservicios, sin 47 capas de abstracción.

## Instalación

```bash
# 1. Dependencias (solo Flask)
python3 -m pip install -r requirements.txt

# 2. Arrancar
python3 app.py

# 3. Abrir
# http://localhost:5000
```

## Flujo

```
TEMA
 ↓
INVESTIGACIÓN
 ↓
CONCEPTO
 ↓
GUION 5 min ── GUION 1 min
 ↓
ESCENAS (un set por guion, con prompt de imagen)
 ↓
METADATA (YouTube + Shorts)
 ↓
MINIATURAS (prompt visual 16:9 + 9:16)
 ↓
CONTROL DE CALIDAD
 ↓
EXPORTAR
```

## Modos de uso

### Modo manual (por defecto)
La herramienta genera **prompts estructurados** que copias en tu LLM
favorito (ChatGPT, Claude, Gemini). Pegas la respuesta de vuelta y
se parsea automáticamente.

Cero costos. Cero dependencias externas. Tú controlas qué LLM usas.

### Modo API
Configura una clave de OpenAI en `Configuración` y la herramienta
llamará al LLM directamente. Compatible con cualquier endpoint
OpenAI-compatible (LM Studio, Ollama con shim, etc.).

## Editor visual de grafo (por perfil)

Además del flujo guiado por etapas, cada perfil expone un lienzo
estilo n8n en `/profiles/<id>/graph` donde puedes:

- Ver y editar los prompts de las nueve etapas fijas en un solo
  vistazo.
- Añadir nodos custom con tus propios prompts SYS y USER y
  conectarlos entre sí para encadenar su output.
- Mover los nodos con drag & drop; las posiciones se guardan
  solas.
- Ejecutar el grafo paso a paso sobre un proyecto desde
  `/projects/<id>/run`: el runner reutiliza los builders y parsers
  existentes para los nodos fijos y muestra el output en un panel
  lateral con el estado de cada nodo (`idle` / `running` / `ok` /
  `error`).

El grafo se renderiza con React Flow v12 cargado por importmap desde
`esm.sh`, así que no hace falta build step ni dependencias NPM.
Más detalle en `docs/ARCHITECTURE.md` y `docs/DECISIONS.md`.

## Perfiles

Guarda configuraciones reutilizables:
tipo de contenido, audiencia, tono, estilo, niveles de misterio/drama,
velocidad de narración y plataformas objetivo.

Ejemplo incluido: **Todo Sobre Todo / Misterio**.

## Control de calidad automático

Verifica:
- Existencia de cada etapa
- Número de palabras (rangos por tipo de guion)
- Duración estimada según velocidad
- Presencia de hook, CTA y estructura
- Repeticiones
- Coherencia escenas (mínimo por guion)
- Mínimo de fuentes
- Afirmaciones sin verificar

## Exportación

Cada proyecto se exporta como un ZIP con:

```
PROYECTO.zip
├── 00_RESUMEN.md
├── 01_investigacion.md
├── 02_concepto.md
├── 03_guiones/
│   ├── guion_long.md
│   └── guion_short.md
├── 04_escenas/
│   └── escenas.md         # un único archivo: TEXTO AUDIO + IMAGEN por escena
├── 05_metadata/
│   ├── metadata_youtube.md
│   └── metadata_shorts.md
├── 06_thumbnails/
│   ├── thumbnail_long.md  # prompt visual 16:9 para el guion 5 min
│   └── thumbnail_short.md # prompt visual 9:16 para el guion 1 min
├── 07_prompts_usados.md   # prompts SYS + USER editados durante el proyecto
└── 08_paquete_completo.json
```

Listo para conectar con tu pipeline de producción.

## Verificación end-to-end

`verify_project.py` ejecuta el flujo completo contra el test client de Flask
utilizando datos simulados del LLM. Crea un proyecto sintético con
`PROJECT_ID=2` si no existe, pasa por las 7 etapas, ejecuta el control de
calidad y genera el ZIP.

```bash
python verify_project.py
```

Útil para detectar regresiones sin depender de un LLM real.

## Tests

```bash
python test_core.py
```

Cubre parsers, utilidades, QC engine y exportación.

## Principios

1. **Simple** — pocos botones, pocas decisiones.
2. **Modular** — cada etapa funciona por separado.
3. **Reutilizable** — perfiles, estilos y configuraciones guardados.
4. **Editable** — la IA propone, tú apruebas.
5. **Sin duplicación** — la información se introduce una sola vez.

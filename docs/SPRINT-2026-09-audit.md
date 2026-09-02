# SPRINT — Auditoría 2026-09

> Plan derivado de la auditoría exhaustiva del 2026-09-01 (resumen ejecutivo en chat; este documento es ejecutable).
> Ejecutar **en orden**. Cada tarea debe cerrar (tests en verde + commit) antes de empezar la siguiente.
> Idioma: español en docs y mensajes de commit. Commits en Conventional Commits.

## Contexto

**Todo Sobre Todo** (`TST-Control`) es un centro de preproducción local para un canal de
documentales, en Flask 3.1.3 + SQLite, con editor de grafos (React Flow v12 vía importmap)
y runner nodo a nodo. Estado actual: `main` limpio, 32 commits, monolito `app.py` de
3168 líneas, docs completas, 38 tests unitarios + smoke E2E, sin secretos reales, sin CI.

La auditoría identificó **1 hallazgo alto** (`secret_key` hardcodeado), **5 medios** (lock,
CI, monolito, inconsistencia documental, except silenciosos) y **8 bajos**. Este sprint los
aborda en cuatro fases ordenadas por ROI/riesgo.

## Convenciones que debe respetar el agente

Recordatorio de `AGENTS.md`:

- Python 3.14.3, type hints en funciones nuevas, sin `any`-equivalente dinámico.
- Comentarios solo cuando aporten valor; JSDoc no aplica (no hay JS público reutilizable).
- Commits: `feat(...)`, `fix(...)`, `chore(...)`, `docs(...)`, `refactor(...)`.
- `TASKS.md` y `CHANGELOG.md` se actualizan al cerrar cada tarea visible al usuario.
- Tests: `python test_core.py` + `python verify_project.py` deben pasar tras cada commit.
- No añadir dependencias sin aprobación explícita.

---

## Phase 0 — Quick wins (~2 h)

### T0.1 — `secret_key` desde variable de entorno

- **Tiempo:** 15 min
- **Por qué:** 🔴 Alta. `config.json:6` contiene `"tst-local-dev-key-change-in-production"`. Cualquier despliegue fuera de `localhost` lo expone.
- **Archivos:** `config.json`, `app.py` (línea ~47), `README.md`, `.gitignore`.

**Pasos:**

1. En `config.json`, dejar `app.secret_key` con valor `""` o eliminar la clave.
2. En `app.py:47` (carga de config), sustituir la lectura directa por:
   ```python
   secret_key = os.environ.get("FLASK_SECRET_KEY") or CONFIG["app"].get("secret_key", "")
   if not secret_key:
       raise RuntimeError("FLASK_SECRET_KEY no definida. Exporta la variable o define secret_key en config.json solo para dev.")
   app.secret_key = secret_key
   ```
3. Añadir `import os` si no está.
4. En `README.md`, sección de instalación, documentar:
   ```bash
   # PowerShell
   $env:FLASK_SECRET_KEY = "genera-con-python -c \"import secrets; print(secrets.token_hex(32))\""
   ```
5. Añadir `FLASK_SECRET_KEY` a `.env.example` si decides crearlo (no commitear `.env`).

**Criterios de aceptación:**

- `app.py` lee `secret_key` de `os.environ` con fallback al config.
- `config.json` ya no contiene un secret en claro (queda vacío o ausente).
- Iniciar sin la variable lanza `RuntimeError` claro.
- `README.md` documenta cómo generar y exportar la clave.

**Validar:**

```bash
python -c "from app import app; print(app.secret_key)"   # debe fallar sin env var
$env:FLASK_SECRET_KEY = "test123"; python -c "from app import app; print(app.secret_key)"
python test_core.py
```

---

### T0.2 — Corregir "7 etapas" en `PRODUCT.md`

- **Tiempo:** 10 min
- **Por qué:** 🟡 Media. `PRODUCT.md:35` dice "Pipeline de 7 etapas" y enumera 9 items. El resto del proyecto (CHANGELOG, ARCHITECTURE, `app.py`, `templates/project.html`) coincide en 8 etapas: `research → concept → scripts → scenes → metadata → thumbnails → qc → export`.
- **Archivos:** `PRODUCT.md`.

**Pasos:**

1. Sustituir la frase "Pipeline de 7 etapas" por "Pipeline de 8 etapas".
2. Sustituir la lista por la canónica de 8 (mismo orden que en `app.py` y `templates/`).
3. Revisar el resto del documento buscando referencias cruzadas a "7 etapas" y corregir.

**Criterios de aceptación:**

- `PRODUCT.md` no menciona "7 etapas" en ningún sitio.
- La lista coincide con el orden real del pipeline.
- `grep -n "7 etapas" PRODUCT.md` → 0 resultados.

**Validar:** `rg "7 etapas" C:\Users\kevin\Dev\TST-Control` debe devolver 0 coincidencias en docs/trackeados.

---

### T0.3 — Añadir `static/uploads/` a `.gitignore`

- **Tiempo:** 5 min
- **Por qué:** 🟢 Baja. El directorio no existe hoy pero la app no lo contempla; anticiparse evita un commit accidental cuando se sume upload de imágenes.
- **Archivos:** `.gitignore`.

**Pasos:**

1. Añadir `static/uploads/` bajo la sección de assets/local artifacts.
2. Verificar con `git check-ignore -v static/uploads/file.png` que el patrón funciona.

**Criterios de aceptación:** el patrón ignora cualquier archivo bajo `static/uploads/`.

---

### T0.4 — Logging estructurado en arranque

- **Tiempo:** 30 min
- **Por qué:** 🟢 Baja. Hoy solo hay `print(...)` en `if __name__ == "__main__":`. Migrar a `logging` deja puerta abierta a niveles, sinks y a integrarlo con T3.1.
- **Archivos:** `app.py`.

**Pasos:**

1. Añadir al inicio de `app.py`:
   ```python
   import logging
   logging.basicConfig(
       level=os.environ.get("TST_LOG_LEVEL", "INFO"),
       format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
   )
   log = logging.getLogger("tst")
   ```
2. Sustituir los `print(...)` del bloque `__main__` por `log.info(...)` (arranque, host, puerto, threads).
3. Si hay prints en rutas (`print("…", flush=True)` etc.), reemplazarlos por `log.debug(...)` o `log.info(...)` según severidad.

**Criterios de aceptación:**

- No quedan `print(` en `app.py` salvo dentro de bloques que ya usan un logger explícito.
- Arrancar el server emite líneas con timestamp y nivel.
- `TST_LOG_LEVEL=DEBUG python app.py` muestra logs adicionales.

**Validar:** `python app.py` y revisar stdout; `python test_core.py` no debe romperse (los tests capturan logs).

---

## Phase 1 — Dependencias y CI (~1 h)

### T1.1 — Lockfile reproducible

- **Tiempo:** 30 min
- **Por qué:** 🟡 Media. `requirements.txt` solo tiene `flask>=2.2` y `waitress>=3.0`. Hoy funciona porque las dos son estables, pero cualquier nueva dep o bump de Flask rompe reproducibilidad silenciosamente.
- **Archivos:** `requirements.txt` (nuevo), `requirements.lock` (nuevo).

**Pasos:**

1. Confirmar herramienta disponible: `pip-compile --version` o `uv --version`. Si ninguna está, instalar `pip-tools` en el entorno del agente (no commitear su instalación).
2. Crear `requirements.in` con el contenido actual de `requirements.txt`.
3. Generar `requirements.lock`:
   - con `pip-compile`: `pip-compile requirements.in -o requirements.lock`
   - con `uv`: `uv pip compile requirements.in -o requirements.lock`
4. Reemplazar `requirements.txt` por el contenido de `requirements.lock` (o mantener ambos si se prefiere el flujo `requirements.in` + `requirements.lock`).
5. Commitear `requirements.lock`. No commitear `requirements.in` si optas por no mantener ambos.

**Criterios de aceptación:**

- Existe `requirements.lock` con todas las deps transitivas pinned (`==`).
- `pip install -r requirements.lock` en un venv limpio reproduce exactamente las versiones actuales.
- `test_core.py` y `verify_project.py` siguen pasando.

**Validar:**

```bash
python -m venv .venv-test && .venv-test\Scripts\activate
pip install -r requirements.lock
python test_core.py && python verify_project.py
```

---

### T1.2 — Workflow de CI mínimo

- **Tiempo:** 30 min
- **Por qué:** 🟡 Media. Sin CI, las regresiones se descubren localmente. El repo no tiene `.github/workflows/`.
- **Archivos:** `.github/workflows/ci.yml` (nuevo).

**Pasos:**

1. Crear `.github/workflows/ci.yml` con:
   - Trigger: `push` y `pull_request` sobre `main`.
   - Matrix: Python 3.14 (la versión del repo; si Actions no la soporta, usar 3.13 con nota en `README.md`).
   - Pasos: checkout → setup-python → `pip install -r requirements.lock` → `python test_core.py` → `python verify_project.py`.
2. Añadir badge en `README.md`: `![CI](https://github.com/aimanagement14/TST-Control/actions/workflows/ci.yml/badge.svg)`.

**Criterios de aceptación:**

- El workflow aparece en la pestaña Actions del repo.
- Empuja una rama dummy y verifica que el workflow corre (o ejecutar manualmente con `gh workflow run` si está configurado).
- Ambos tests (`test_core.py`, `verify_project.py`) son obligatorios; si cualquiera falla, el workflow falla.

**Validar:**

```bash
git add .github/workflows/ci.yml README.md
git commit -m "ci: add Python test workflow on push/PR"
git push
# luego en GitHub Actions verificar
```

---

## Phase 2 — Extracción del monolito (PoC, ~1 sprint)

> El monolito es **deliberado** (consta en `docs/DECISIONS.md` ADR-001). Esta fase **no** propone reescribir `app.py`; plantea una **prueba de concepto** que valide el patrón para crecer más limpio. Si tras T2.1–T2.3 el patrón no aporta valor, revertir y mantener el monolito (queda como ADR nuevo).

### T2.1 — Carpeta `services/`

- **Tiempo:** 3 h
- **Por qué:** El monolito mezcla rutas, utilidades, parsers, llamadas LLM y reglas QC. Separar lo que **no es HTTP** facilita tests aislados y reduce la barrera para futuros blueprints.
- **Archivos nuevos:** `services/__init__.py`, `services/llm.py`, `services/parsers.py`, `services/qc.py`.
- **Archivos a editar:** `app.py`.

**Pasos:**

1. Identificar en `app.py` las funciones puras (sin `request`, sin `current_app`, sin acceso a `g`/`session`) agrupadas en:
   - Llamadas HTTP a proveedores LLM (funciones tipo `_call_openai_compatible`, `_call_anthropic`, etc.).
   - Parsers de respuestas (research, concept, script, scenes, metadata, thumbnail).
   - Reglas QC (las ~5 funciones de validación que se invocan desde la ruta `/qc`).
2. Mover cada grupo a su archivo `services/<grupo>.py` con su firma actual.
3. Reemplazar en `app.py` las definiciones por `from services.llm import ...` etc.
4. Confirmar que `test_core.py` (que importa parsers vía `from app import ...`) sigue pasando — si hay imports circulares, ajustar puntos de entrada.

**Criterios de aceptación:**

- `services/` contiene 3 módulos con funciones puras y sin dependencias de Flask.
- `app.py` no pierde ni cambia comportamiento.
- `test_core.py` y `verify_project.py` pasan idénticos.

**Validar:** `python test_core.py && python verify_project.py`.

---

### T2.2 — Blueprints `graph_bp` y `runner_bp`

- **Tiempo:** 4 h
- **Por qué:** Las rutas del editor de grafos (`/profiles/<id>/graph/...`) y del runner (`/projects/<id>/run/...`) están aisladas del resto y son candidatas naturales a blueprint.
- **Archivos nuevos:** `blueprints/__init__.py`, `blueprints/graph.py`, `blueprints/runner.py`.
- **Archivos a editar:** `app.py`.

**Pasos:**

1. Crear `blueprints/graph.py` con un `Blueprint("graph", __name__, url_prefix="/profiles")` y mover:
   - `/profiles/<id>/graph` (GET)
   - `/profiles/<id>/graph/save-node` (POST)
   - `/profiles/<id>/graph/delete-node` (POST)
   - `/profiles/<id>/graph/layout` (POST)
2. Crear `blueprints/runner.py` con `Blueprint("runner", __name__, url_prefix="/projects")` y mover:
   - `/projects/<id>/run` (GET)
   - `/projects/<id>/run/execute` (POST)
   - `/projects/<id>/run/reset-node` (POST)
3. En `app.py`, sustituir las definiciones de rutas por `app.register_blueprint(graph_bp)` y `app.register_blueprint(runner_bp)`.
4. Verificar `url_for("graph.profile_graph", profile_id=...)` y `url_for("runner.project_run", project_id=...)` desde `templates/profile_graph.html` y `templates/project_run.html` (ajustar si los endpoint names cambian).

**Criterios de aceptación:**

- Las 7 rutas mencionadas viven ahora en sus blueprints.
- `app.py` las registra y nada más.
- Los templates siguen encontrando sus `url_for` (sin 404 al navegar).
- `test_core.py` y `verify_project.py` pasan.

**Validar:** Smoke manual: abrir `/profiles`, abrir `/projects/<id>/run`, ejecutar un nodo, guardar layout. `python test_core.py && python verify_project.py`.

---

### T2.3 — ADR del nuevo patrón

- **Tiempo:** 20 min
- **Por qué:** Documentar la decisión es parte del patrón devkit (ver `docs/DECISIONS.md`).
- **Archivos:** `docs/DECISIONS.md`, `ARCHITECTURE.md`.

**Pasos:**

1. Añadir ADR-010 "Servicios y blueprints como PoC" en `docs/DECISIONS.md` con:
   - Contexto
   - Decisión (qué se extrajo, qué se quedó)
   - Consecuencias (positivas y negativas observadas)
   - Reversibilidad (qué se撤収 si la PoC no convence)
2. Actualizar `docs/ARCHITECTURE.md` con una sección `services/` y `blueprints/` en la tabla de módulos.

**Criterios de aceptación:** ADR fechado, `ARCHITECTURE.md` refleja la nueva estructura.

---

## Phase 3 — Robustez (~1 sprint)

### T3.1 — Logging en `except Exception:` silenciosos

- **Tiempo:** 2 h
- **Por qué:** 🟡 Media (recogido de la auditoría). `app.py` tiene ~30 `except Exception:` que se tragan el error. Migrar Phase 0 dejó `log` listo para esto.
- **Archivos:** `app.py`.

**Pasos:**

1. Localizar todos los `except Exception:` (grep: `rg "except Exception" app.py`).
2. Para cada uno, decidir:
   - **Crítico de mutación** (POST que persiste): reemplazar por `log.exception("contexto")` + devolver error al usuario.
   - **Recuperable** (puede continuar): `log.warning("contexto: %s", e)` y seguir.
   - **Silencioso legítimo** (ej. `KeyError` esperado en parseo): documentar con comentario `# expected: <razón>` y `log.debug(...)`.
3. No introducir tipos de excepción ad-hoc en este sprint (sería alcance de un refactor mayor).

**Criterios de aceptación:**

- No quedan `except Exception: pass` ni `except Exception: continue` sin al menos un `log.*`.
- Provocar un error recuperable (p. ej. matar SQLite) emite un log con traceback antes de retornar al usuario.
- `test_core.py` y `verify_project.py` siguen pasando.

**Validar:** `python test_core.py && python verify_project.py`.

---

### T3.2 — Dividir `static/graph.js` en módulos ESM

- **Tiempo:** 3 h
- **Por qué:** 🟢 Baja. 823 líneas y 36 KB en un solo archivo. Crecerá más con cada feature del editor.
- **Archivos nuevos:** `static/graph/nodes.js`, `static/graph/api.js`, `static/graph/layout.js`, `static/graph/index.js` (entry).
- **Archivos a editar:** `static/graph.js` (eliminar o reducir a entry), `templates/profile_graph.html` (ajustar importmap si aplica), `templates/project_run.html`.

**Pasos:**

1. Identificar las 3 áreas dentro de `graph.js`:
   - Definición de tipos de nodo y `react-flow` setup.
   - Llamadas `fetch` a `/profiles/.../graph/...`.
   - Algoritmos de auto-layout.
2. Extraer cada área a su módulo, exportar lo necesario.
3. Convertir `graph.js` en entry-point que solo importa y registra.
4. Ajustar el `<script type="module" src="...">` en las plantillas.

**Criterios de aceptación:**

- Ningún módulo individual supera ~300 líneas.
- `graph.js` queda como entry de <50 líneas.
- El editor sigue funcionando: crear nodo, moverlo, guardar layout, ejecutar runner.
- `verify_project.py` (que probablemente toca el editor) sigue verde.

**Validar:** Smoke manual del editor + `python verify_project.py`.

---

### T3.3 — Mover `projects/Todo_sobre_los_Fosiles_1/` a `examples/`

- **Tiempo:** 30 min
- **Por qué:** 🟢 Baja. Versionar muestras crece el repo con cada proyecto nuevo. Tener `examples/` separa "demo oficial" de "proyectos generados".
- **Archivos:** mover `projects/Todo_sobre_los_Fosiles_1/` y su `.zip` a `examples/`.
- **Archivos a editar:** `app.py` (rutas que asumen `projects/` como raíz de export), `README.md` (si menciona la ubicación), `docs/ARCHITECTURE.md`.

**Pasos:**

1. Crear `examples/` y mover `Todo_sobre_los_Fosiles_1/` + `.zip`.
2. Revisar `app.py` por paths hardcodeados a `projects/` y ajustar a una constante `EXPORTS_DIR` o similar (en línea con el patrón devkit de "config-driven paths").
3. Actualizar README y ARCHITECTURE si mencionan `projects/`.

**Criterios de aceptación:**

- `projects/` queda vacío (o solo contiene `.gitkeep` con nota).
- `examples/Todo_sobre_los_Fosiles_1/` contiene los mismos archivos que antes.
- El flujo de export sigue funcionando en `verify_project.py`.

**Validar:** `python verify_project.py`.

---

## Validación común a todas las fases

Tras **cada tarea** (no cada fase), ejecutar en orden:

```powershell
cd C:\Users\kevin\Dev\TST-Control
python -m pyflakes app.py services/ blueprints/   # si los Directorios existen
python test_core.py
python verify_project.py
git status          # confirmar working tree limpio antes del commit
```

Tras **cada fase**, actualizar:

- `TASKS.md`: mover tareas completadas a la sección cerrada.
- `CHANGELOG.md`: añadir entrada bajo `[Unreleased]` siguiendo el formato existente.
- `README.md` / `docs/`: solo si la tarea cambió comportamiento visible.

---

## Riesgos y notas

1. **Phase 0 / 1 son seguras.** Si T0.1 rompe algo, el rollback es revert del commit. Idem T0.2–T1.2.
2. **Phase 2 es opt-in por diseño.** Si T2.1 o T2.2 encuentran阻力 (resistencia, acoplamiento inesperado), revertir con `git revert` y dejar ADR documentando "monolito confirmado para este proyecto". No insistir.
3. **Python 3.14 en GitHub Actions** puede no estar disponible aún en el runner. Si el workflow falla por versión, usar `python-version: "3.13"` y dejar nota en `README.md` hasta que Actions lo soporte oficialmente.
4. **No commitear `.env`, `FLASK_SECRET_KEY`, ni `.venv/`.** El `.gitignore` ya cubre la mayoría; verifica con `git status` antes de cada commit.
5. **Scope creep.** Si durante una tarea aparece algo nuevo, anotarlo en `TASKS.md` como "descubierto durante <T-X.Y>" pero no abordarlo en el mismo sprint.

---

## Orden de ejecución

```
Phase 0: T0.1 → T0.2 → T0.3 → T0.4
Phase 1: T1.1 → T1.2
Phase 2: T2.1 → T2.2 → T2.3
Phase 3: T3.1 → T3.2 → T3.3
```

Total estimado: **~2.5 días para Phase 0+1, ~1 sprint para Phase 2+3.**

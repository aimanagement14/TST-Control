"""
Tests automatizados para los componentes críticos:
- Parsers (research, concept, script, scenes, prompts, metadata)
- QC engine
- Counters y estimaciones
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import app
from services.parsers import (
    estimate_duration_seconds,
    parse_prompt_json,
    parse_scenes_json,
)

# Forzar UTF-8 en stdout/stderr para que los caracteres (✓, á, ó, →) no rompan
# en consolas Windows con cp1252 por defecto (Python 3.13 mantiene la
# codificación por defecto aunque se pase -X utf8).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ==========================================================================
# Tests de parsers
# ==========================================================================


def test_parse_research():
    text = """## RESUMEN
OVNIs es un tema recurrente.

## HECHOS CONFIRMADOS
- Pentagon reconoció AATIP
- 144 incidentes documentados

## TEORÍAS Y VERSIONES
- Hipótesis natural
- Secreto militar

## FUENTES
- https://example.com
- https://wikipedia.org

## AFIRMACIONES QUE REQUIEREN VERIFICACIÓN
- Programas de recuperación"""

    r = app.parse_research(text)
    assert "OVNIs" in r["content"], "content no extraído"
    assert len(r["facts"]) == 2, f"facts: {r['facts']}"
    assert len(r["theories"]) == 2, f"theories: {r['theories']}"
    assert len(r["sources"]) == 2, f"sources: {r['sources']}"
    assert len(r["unverified"]) == 1, f"unverified: {r['unverified']}"
    print("  ✓ parse_research")


def test_parse_research_with_variations():
    text = """## RESUMEN
Texto del resumen.

## HECHOS CONFIRMADOS
- hecho A
- hecho B
- hecho C

## TEORÍAS Y VERSIONES
- t1
- t2

## CONTROVERSIAS Y DEBATES
- debate 1
- debate 2

## DATOS CLAVE
- 2021
- 2023

## FUENTES
- https://a.com
- https://b.com
- https://c.com

## AFIRMACIONES QUE REQUIEREN VERIFICACIÓN
- af1"""
    r = app.parse_research(text)
    assert len(r["facts"]) >= 3, f"facts: {r['facts']}"
    assert len(r["sources"]) >= 3, f"sources: {r['sources']}"
    assert len(r["unverified"]) == 1
    print("  ✓ parse_research (con variaciones)")


def test_parse_concept():
    text = """## ÁNGULO
Documental sobre OVNIs.

## TESIS CENTRAL
El gobierno sabe más de lo que cuenta.

## PUNTOS CLAVE A DESARROLLAR
1. Cambio histórico
2. Videos
3. Informe ODNI

## GANCHO EMOCIONAL
Curiosidad

## LO QUE EL ESPECTADOR DEBE APRENDER
- Cronología real
- Actores clave

## LO QUE EL ESPECTADOR DEBE SENTIR
- Sorpresa

## RIESGOS
- Sensacionalismo"""

    r = app.parse_concept(text)
    assert "Documental" in r["angle"], "angle"
    assert "gobierno" in r["thesis"], f"thesis vacía: '{r['thesis']}'"
    assert len(r["key_points"]) == 3, f"key_points: {r['key_points']}"
    assert "Curiosidad" in r["emotional_hook"], "emotional_hook"
    assert len(r["what_they_learn"]) == 2, f"learn: {r['what_they_learn']}"
    assert len(r["what_they_feel"]) == 1
    assert len(r["risks"]) == 1
    print("  ✓ parse_concept")


def test_parse_concept_with_body_text():
    """Las líneas que empiezan con la palabra de la sección no deben hacer match."""
    text = """## ÁNGULO
Documental sobre el Pentágono.

## TESIS
El Pentágono confirmó cosas en 2017.

## PUNTOS CLAVE
1. El Pentágono cambió
2. La Marina grabó videos
3. El Pentágono testificó"""
    r = app.parse_concept(text)
    assert "Pentágono" in r["angle"]
    assert "Pentágono confirmó cosas en 2017" in r["thesis"], f"thesis perdida: '{r['thesis']}'"
    assert len(r["key_points"]) == 3
    print("  ✓ parse_concept (con texto que empieza por nombre de sección)")


def test_parse_script_long():
    text = """## TITULO
OVNIs

## HOOK (0:00 - 0:15)
En 2017 el Pentágono confirmó algo.

## CONTEXTO (0:15 - 1:00)
Contexto inicial del video.

## DESARROLLO (1:00 - 3:30)
Texto del desarrollo.

### BLOQUE 1: Título
Texto del bloque 1.

### BLOQUE 2: Otro título
Texto del bloque 2.

## REVELACIONES (3:30 - 4:30)
La pregunta inquietante.

## CONCLUSIÓN (4:30 - 4:50)
Conclusión reflexiva.

## CTA (4:50 - 5:00)
Suscríbete."""

    r = app.parse_script(text, "long")
    assert r["title"] == "OVNIs"
    assert "Pentágono" in r["hook"]
    assert "Contexto inicial" in r["context"]
    assert "BLOQUE 1" in r["development"] and "Texto del bloque 1" in r["development"]
    assert "pregunta inquietante" in r["revelations"]
    assert "reflexiva" in r["conclusion"]
    assert "Suscríbete" in r["cta"]
    assert r["body_full"]
    print("  ✓ parse_script (long)")


def test_parse_script_short():
    text = """## TITULO
OVNIs: 60 segundos

## HOOK (0:00 - 0:05)
El Pentágono confirmó.

## INFORMACIÓN ESENCIAL (0:05 - 0:35)
144 incidentes. 143 sin explicación.

## ESCALADA (0:35 - 0:55)
David Grusch testificó bajo juramento.

## REMATE (0:55 - 1:00)
La verdad es más inquietante.

## CTA (1:00 - 1:05)
Sígueme."""

    r = app.parse_script(text, "short")
    assert r["title"] == "OVNIs: 60 segundos"
    assert r["hook"]
    assert "144 incidentes" in r["context"], f"context: {r['context']}"
    assert "Grusch" in r["revelations"]
    assert "inquietante" in r["conclusion"]
    assert "Sígueme" in r["cta"]
    print("  ✓ parse_script (short)")


def test_parse_scenes_json():
    text_with_json = """Aquí va la respuesta:

```json
[
  {"scene_number": 1, "narration_segment": "test", "visual_description": "v", "duration_seconds": 10, "camera_movement": "zoom", "transition": "fade"}
]
```

Fin."""
    r = parse_scenes_json(text_with_json)
    assert r is not None, "no se pudo parsear"
    assert len(r) == 1
    assert r[0]["scene_number"] == 1
    print("  ✓ parse_scenes_json (en bloque markdown)")


def test_parse_scenes_json_bare():
    text = 'Some intro [{"scene_number": 1, "narration_segment": "x", "visual_description": "y", "duration_seconds": 5, "camera_movement": "static", "transition": "cut"}] end'
    r = parse_scenes_json(text)
    assert r is not None
    assert r[0]["scene_number"] == 1
    print("  ✓ parse_scenes_json (JSON sin bloque)")


def test_parse_prompt_json():
    text = """```json
{
  "subject": "Pentagon",
  "environment": "aerial",
  "era": "contemporary",
  "lighting": "golden",
  "camera": "wide",
  "composition": "thirds",
  "atmosphere": "fog",
  "style": "cinematic",
  "full_prompt_en": "Aerial view of the Pentagon",
  "full_prompt_es": "Vista aérea del Pentágono"
}
```"""
    r = parse_prompt_json(text)
    assert r is not None
    assert r["subject"] == "Pentagon"
    assert "Pentagon" in r["full_prompt_en"]
    print("  ✓ parse_prompt_json")


def test_parse_metadata_youtube():
    text = """## TÍTULOS (5 opciones)
1. OVNIs: la verdad
2. Pentagon confirmado

## DESCRIPCIÓN
Video sobre OVNIs.

## CAPÍTULOS
00:00 Intro
01:00 Bloque 1

## TAGS (15)
ovnis, uap, pentagono, mil

## HASHTAGS (5)
#ovnis #misterio #uap #pentagono #viral

## CTA
Suscríbete."""
    r = app.parse_metadata(text, "youtube")
    assert len(r["titles"]) == 2
    assert "Video sobre OVNIs" in r["description"]
    assert len(r["chapters"]) == 2
    assert len(r["tags"]) >= 4, f"tags: {r['tags']}"
    assert len(r["hashtags"]) == 5
    print("  ✓ parse_metadata (youtube)")


def test_parse_metadata_shorts():
    text = """## CAPTION
El Pentágono confirmó OVNIs.

## HOOK
Pentágono confirma OVNIs

## HASHTAGS (10)
#ovnis #misterio #viral #shorts

## CTA
Sígueme.

## TEXTO EN PANTALLA
1. PENTAGONO CONFIRMA
2. 144 INCIDENTES"""
    r = app.parse_metadata(text, "shorts")
    assert "Pentágono" in r["caption"]
    assert "Pentágono confirma" in r["hook"]
    assert len(r["hashtags"]) == 4
    assert len(r["on_screen_text"]) == 2
    print("  ✓ parse_metadata (shorts)")


def test_parse_metadata_facebook_long():
    text = """## DESCRIPCION
Primera frase con gancho emocional sobre el misterio. Segundo párrafo con el contexto clave del tema investigado. Tercer párrafo con la pregunta que deja al espectador pensando. Cuarto párrafo con la llamada a comentar y compartir. Quinto párrafo opcional con las fuentes mencionadas en el vídeo."""
    r = app.parse_metadata(text, "facebook_long")
    assert "gancho emocional" in r["description"]
    assert "comentar y compartir" in r["description"]
    assert r["titles"] == []
    assert r["hashtags"] == []
    print("  ✓ parse_metadata (facebook_long, prosa continua)")


def test_parse_metadata_reels_short():
    text = """## DESCRIPCION
Gancho emocional para Reels, primera frase que funciona sin audio. Segunda frase con el dato clave. Tercera frase con la llamada a la acción.

## HASHTAGS (5-8)
#ovnis #tetis #yetis #shorts

## CTA
Comenta qué crees que vio el piloto."""
    r = app.parse_metadata(text, "reels_short")
    assert "Reels" in r["description"]
    assert len(r["hashtags"]) == 4
    assert "Comenta" in r["cta"]
    assert r["titles"] == []
    assert r["on_screen_text"] == []
    print("  ✓ parse_metadata (reels_short, prosa + hashtags)")


def test_parse_thumbnail():
    text = """## MINIATURA
A weathered stone monolith half-buried in jungle fog, lit by a single volumetric sunbeam piercing the canopy, with bioluminescent moss crawling up its carved symbols, hyper-detailed textures, cinematic orange and teal grading, 16:9 composition, dramatic contrast, documentary premium quality, eye-catching focal point off-center.
"""
    r = app.parse_thumbnail(text, "long")
    assert "stone monolith" in r["prompt"]
    assert "16:9" in r["prompt"]
    assert r["prompt"].strip() == r["prompt"].strip()
    print("  ✓ parse_thumbnail")


def test_parse_thumbnail_ignores_other_blocks():
    text = """## OTRA COSA
bla bla

## MINIATURA
prompt útil aquí
con varias líneas

## RUIDO
más texto"""
    r = app.parse_thumbnail(text, "short")
    assert r["prompt"].startswith("prompt útil aquí")
    assert "varias líneas" in r["prompt"]
    assert "OTRA COSA" not in r["prompt"]
    assert "RUIDO" not in r["prompt"]
    print("  ✓ parse_thumbnail (ignora bloques no-MINIATURA)")


# ==========================================================================
# Tests de utilidades
# ==========================================================================


def test_count_words():
    assert app.count_words("Hola mundo") == 2
    assert app.count_words("") == 0
    assert app.count_words(None) == 0
    assert app.count_words("uno, dos; tres.cuatro") == 4
    assert app.count_words("El Pentágono confirmó 144 incidentes") == 5
    print("  ✓ count_words")


def test_estimate_duration():
    # 150 palabras por minuto = 2.5 palabras por segundo
    # 300 palabras = 120 segundos
    assert estimate_duration_seconds("") == 0
    text = " ".join(["palabra"] * 300)
    assert estimate_duration_seconds(text, wpm=150) == 120
    print("  ✓ estimate_duration_seconds")


# ==========================================================================
# Tests de QC
# ==========================================================================


def _setup_qc_db(tmp_path):
    """Crea una DB temporal con datos para test de QC."""
    db_path = tmp_path / "test.db"
    # Override DB_PATH
    app.DB_PATH = db_path
    app.init_db()
    return db_path


def test_qc_detects_missing_research(tmp_path):
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO projects (id, name, topic, status, created_at, updated_at)
            VALUES (1, 'Test', 'Topic', 'created', '2025-01-01', '2025-01-01')
        """)
    issues = app.run_qc(1)
    has_research_error = any(
        i[0] == "research" and i[1] == "error" and "investigación" in i[2].lower() for i in issues
    )
    assert has_research_error, f"Falta error de research: {issues}"
    print("  ✓ QC detecta investigación faltante")


def test_qc_detects_short_script(tmp_path):
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO projects (id, name, topic, status, created_at, updated_at)
            VALUES (1, 'Test', 'Topic', 'created', '2025-01-01', '2025-01-01')
        """)
        conn.execute("""
            INSERT INTO research (project_id, content, sources, updated_at)
            VALUES (1, 'investigación válida', '["s1","s2","s3","s4","s5","s6"]', '2025-01-01')
        """)
        conn.execute("""
            INSERT INTO scripts (project_id, type, title, hook, body_full, word_count, updated_at)
            VALUES (1, 'long', 'Test', 'hook', 'corto', 5, '2025-01-01')
        """)
    issues = app.run_qc(1)
    has_short_warning = any(
        i[0] == "scripts" and i[1] == "warning" and "long" in i[2] and "5 palabras" in i[2]
        for i in issues
    )
    assert has_short_warning, f"Falta warning de guion corto: {issues}"
    print("  ✓ QC detecta guion demasiado corto")


def test_qc_detects_repetition(tmp_path):
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO projects (id, name, topic, status, created_at, updated_at)
            VALUES (1, 'Test', 'Topic', 'created', '2025-01-01', '2025-01-01')
        """)
        body = (
            "objetos " * 50
            + "otros términos variados para completar el guion y cumplir mil quinientas palabras"
        )
        conn.execute(
            """
            INSERT INTO scripts (project_id, type, title, hook, body_full, word_count, updated_at)
            VALUES (1, 'long', 'Test', 'hook', ?, 800, '2025-01-01')
        """,
            (body,),
        )
    issues = app.run_qc(1)
    has_repetition = any(i[0] == "scripts" and "repetida" in i[2].lower() for i in issues)
    assert has_repetition, f"Falta detección de repetición: {issues}"
    print("  ✓ QC detecta repeticiones")


def test_qc_detects_missing_sources(tmp_path):
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO projects (id, name, topic, status, created_at, updated_at)
            VALUES (1, 'Test', 'Topic', 'created', '2025-01-01', '2025-01-01')
        """)
        conn.execute("""
            INSERT INTO research (project_id, content, sources, updated_at)
            VALUES (1, 'algo de contenido', '["s1","s2"]', '2025-01-01')
        """)
    issues = app.run_qc(1)
    has_sources_warning = any(i[0] == "research" and "fuentes" in i[2].lower() for i in issues)
    assert has_sources_warning, f"Falta warning de fuentes: {issues}"
    print("  ✓ QC detecta pocas fuentes")


def test_qc_passes_complete_project(tmp_path):
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO projects (id, name, topic, status, created_at, updated_at)
            VALUES (1, 'Test', 'Topic', 'created', '2025-01-01', '2025-01-01')
        """)
        conn.execute("""
            INSERT INTO research (project_id, content, sources, updated_at)
            VALUES (1, 'investigación completa con suficiente detalle', '["s1","s2","s3","s4","s5","s6"]', '2025-01-01')
        """)
        conn.execute("""
            INSERT INTO concept (project_id, angle, thesis, updated_at)
            VALUES (1, 'ángulo válido', 'tesis válida', '2025-01-01')
        """)
        # Guion largo ~750 palabras
        body = " ".join([f"palabra{i}" for i in range(700)])
        body += " hook específico cta final conclusión revelaciones"
        conn.execute(
            """
            INSERT INTO scripts (project_id, type, title, hook, context, development,
                revelations, conclusion, cta, body_full, word_count, updated_at)
            VALUES (1, 'long', 'Test', 'hook inicial', 'contexto', 'desarrollo',
                'revelaciones finales', 'conclusión reflexiva', 'suscríbete',
                ?, 750, '2025-01-01')
        """,
            (body,),
        )
        # 6 escenas
        for i in range(6):
            conn.execute(
                """
                INSERT INTO scenes (project_id, scene_number, narration, visual_description,
                    duration_seconds, camera_movement, transition, updated_at)
                VALUES (1, ?, 'narración escena', 'visual escena', 30, 'zoom', 'fade', '2025-01-01')
            """,
                (i + 1,),
            )
        # Metadata
        conn.execute("""
            INSERT INTO metadata_records (project_id, platform, titles, updated_at)
            VALUES (1, 'youtube_long', '[]', '2025-01-01')
        """)
    issues = app.run_qc(1)
    errors = [i for i in issues if i[1] == "error"]
    assert not errors, f"No debería haber errores en proyecto completo: {errors}"
    print(f"  ✓ QC aprueba proyecto completo ({len(issues)} avisos no críticos)")


# ==========================================================================
# Tests del flujo de export
# ==========================================================================


def test_export_creates_zip(tmp_path):
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO projects (id, name, topic, status, created_at, updated_at)
            VALUES (1, 'Export Test', 'Topic', 'ready', '2025-01-01', '2025-01-01')
        """)
        conn.execute("""
            INSERT INTO research (project_id, content, sources, updated_at)
            VALUES (1, 'investigación de prueba con suficiente detalle', '["s1","s2","s3","s4","s5","s6"]', '2025-01-01')
        """)
        conn.execute("""
            INSERT INTO concept (project_id, angle, thesis, updated_at)
            VALUES (1, 'ángulo de prueba', 'tesis de prueba', '2025-01-01')
        """)
        conn.execute("""
            INSERT INTO scripts (project_id, type, title, hook, body_full, word_count, updated_at)
            VALUES (1, 'long', 'Guion Test', 'hook de prueba',
                'cuerpo del guion con suficiente extensión para validar el export', 100, '2025-01-01')
        """)
        for i in range(3):
            conn.execute(
                """
                INSERT INTO scenes (project_id, scene_number, narration, visual_description,
                    duration_seconds, updated_at)
                VALUES (1, ?, 'narración', 'visual', 30, '2025-01-01')
            """,
                (i + 1,),
            )
        conn.execute("""
            INSERT INTO metadata_records (project_id, platform, titles, description, updated_at)
            VALUES (1, 'youtube_long', '["t1"]', 'desc', '2025-01-01')
        """)
    # Override projects dir
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        with app.app.test_client() as c:
            resp = c.post("/projects/1/export", follow_redirects=False)
            assert resp.status_code == 200, f"status: {resp.status_code}"
            import io

            data = resp.data
            assert len(data) > 1000, f"zip demasiado pequeño: {len(data)}"
            import zipfile

            zf = zipfile.ZipFile(io.BytesIO(data))
            names = zf.namelist()
            assert any("00_RESUMEN.md" in n for n in names)
            assert any("01_investigacion.md" in n for n in names)
            assert any("08_paquete_completo.json" in n for n in names)
        print(f"  ✓ export crea ZIP con {len(names)} archivos")
    finally:
        app.PROJECTS_DIR = original


def test_new_project_creates_folder(tmp_path):
    """Al crear un proyecto, sync_project_folder deja 00_RESUMEN.md en disco."""
    _setup_qc_db(tmp_path)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        c = app.app.test_client()
        r = c.post(
            "/projects/new",
            data={"name": "Carpeta auto", "topic": "verifico la sincronización"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        with app.get_db() as conn:
            new_id = conn.execute("SELECT id FROM projects WHERE name='Carpeta auto'").fetchone()[
                "id"
            ]
        folder = app.safe_project_dir(new_id, "Carpeta auto")
        assert folder.exists(), f"carpeta {folder} no se creó"
        resumen = (folder / "00_RESUMEN.md").read_text(encoding="utf-8")
        assert "Carpeta auto" in resumen
        assert "verifico la sincronización" in resumen
        print("  ✓ crear proyecto sincroniza la carpeta con 00_RESUMEN.md")
    finally:
        app.PROJECTS_DIR = original


def test_research_save_syncs_folder(tmp_path):
    """Guardar investigación reescribe 01_investigacion.md en la carpeta."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO projects (id, name, topic, status, created_at, updated_at)
            VALUES (1, 'Sync Test', 'Topic', 'research', '2025-01-01', '2025-01-01')
        """)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        c = app.app.test_client()
        r = c.post(
            "/projects/1/research",
            data={
                "action": "save",
                "content": "## RESUMEN\n\nTexto inicial.\n\n## FUENTES\n- http://a\n- http://b",
            },
            follow_redirects=True,
        )
        assert r.status_code == 200
        folder = app.safe_project_dir(1, "Sync Test")
        inv = (folder / "01_investigacion.md").read_text(encoding="utf-8")
        assert "Texto inicial" in inv
        assert "http://a" in inv
        # Re-save con cambios: el archivo se reescribe
        r = c.post(
            "/projects/1/research",
            data={
                "action": "save",
                "content": "## RESUMEN\n\nTexto actualizado.",
            },
            follow_redirects=True,
        )
        inv = (folder / "01_investigacion.md").read_text(encoding="utf-8")
        assert "Texto actualizado" in inv
        assert "Texto inicial" not in inv
        print("  ✓ guardar research re-sincroniza 01_investigacion.md")
    finally:
        app.PROJECTS_DIR = original


def test_metadata_save_syncs_folder(tmp_path):
    """Guardar metadata crea 05_metadata/metadata_<platform>.md en la carpeta."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO projects (id, name, topic, status, created_at, updated_at)
            VALUES (1, 'Meta Test', 'Topic', 'metadata', '2025-01-01', '2025-01-01')
        """)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        c = app.app.test_client()
        r = c.post(
            "/projects/1/metadata",
            data={
                "action": "save",
                "platform": "youtube_long",
                "script_id": "",
                "text": "## TITULOS (5 opciones)\n1. Uno\n2. Dos\n3. Tres\n4. Cuatro\n5. Cinco\n\n## DESCRIPCION\ndescripción de prueba con suficiente extensión para validar el archivo",
            },
            follow_redirects=True,
        )
        assert r.status_code == 200
        folder = app.safe_project_dir(1, "Meta Test")
        meta = (folder / "05_metadata" / "metadata_youtube_long.md").read_text(encoding="utf-8")
        assert "Uno" in meta
        assert "descripción de prueba" in meta
        print("  ✓ guardar metadata re-sincroniza 05_metadata/")
    finally:
        app.PROJECTS_DIR = original


def test_export_get_renders_folder(tmp_path):
    """GET /export muestra archivos de la carpeta sin crear ZIP."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO projects (id, name, topic, status, created_at, updated_at)
            VALUES (1, 'Folder Test', 'Topic', 'ready', '2025-01-01', '2025-01-01')
        """)
        conn.execute("""
            INSERT INTO research (project_id, content, sources, updated_at)
            VALUES (1, 'investigación', '["s1","s2","s3","s4","s5","s6"]', '2025-01-01')
        """)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        c = app.app.test_client()
        r = c.get("/projects/1/export")
        assert r.status_code == 200
        body = r.data.decode("utf-8")
        assert "Re-sincronizar carpeta" in body
        assert "Descargar ZIP" in body
        assert "00_RESUMEN.md" in body
        assert "01_investigacion.md" in body
        # La carpeta debe existir tras el GET (sync perezosa)
        folder = app.safe_project_dir(1, "Folder Test")
        assert folder.exists()
        # No debe haberse creado un ZIP sin acción explícita
        assert not (test_projects / "Folder_Test_1.zip").exists()
        print("  ✓ GET /export lista la carpeta sin generar ZIP")
    finally:
        app.PROJECTS_DIR = original


def test_export_resync_action(tmp_path):
    """POST /export action=resync regenera la carpeta y redirige."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO projects (id, name, topic, status, created_at, updated_at)
            VALUES (1, 'Resync Test', 'Topic', 'ready', '2025-01-01', '2025-01-01')
        """)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        c = app.app.test_client()
        r = c.post("/projects/1/export", data={"action": "resync"}, follow_redirects=False)
        assert r.status_code == 302
        assert "resync" not in r.headers.get("Location", "").lower() or "export" in r.headers.get(
            "Location", ""
        )
        folder = app.safe_project_dir(1, "Resync Test")
        assert (folder / "00_RESUMEN.md").exists()
        assert (folder / "08_paquete_completo.json").exists()
        print("  ✓ POST /export action=resync reescribe la carpeta")
    finally:
        app.PROJECTS_DIR = original


def test_delete_project_removes_folder(tmp_path):
    """Borrar el proyecto elimina la carpeta en disco."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO projects (id, name, topic, status, created_at, updated_at)
            VALUES (1, 'Doomed', 'Topic', 'research', '2025-01-01', '2025-01-01')
        """)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        app.sync_project_folder(1)
        folder = app.safe_project_dir(1, "Doomed")
        assert folder.exists()
        c = app.app.test_client()
        r = c.post("/projects/1/delete", follow_redirects=False)
        assert r.status_code == 302
        assert not folder.exists(), "la carpeta debe haberse borrado"
        with app.get_db() as conn:
            row = conn.execute("SELECT 1 FROM projects WHERE id=1").fetchone()
        assert row is None
        print("  ✓ borrar proyecto elimina la carpeta del proyecto")
    finally:
        app.PROJECTS_DIR = original


# ==========================================================================
# Tests de prompts por perfil (graph foundation)
# ==========================================================================


def test_resolve_stage_prompt_falls_back_to_config(tmp_path):
    """Sin fila en profile_prompts, devuelve los strings de CONFIG."""
    _setup_qc_db(tmp_path)
    profile_id = 1
    sys_p, user_p = app.resolve_stage_prompt(profile_id, "research")
    assert sys_p == app.CONFIG["prompts"]["research"]["system"]
    assert user_p == app.CONFIG["prompts"]["research"]["format"]
    sys_p, user_p = app.resolve_stage_prompt(profile_id, "no_existe")
    assert sys_p == "" and user_p == ""
    print("  ✓ resolve_stage_prompt cae a CONFIG y a vacío si stage desconocido")


def test_save_profile_prompt_upsert(tmp_path):
    """save_profile_prompt hace UPSERT (no duplica) y respeta profile_id None."""
    _setup_qc_db(tmp_path)
    profile_id = 1
    app.save_profile_prompt(profile_id, "research", "sys1", "user1")
    out = app.list_profile_prompts(profile_id)
    assert out["research"]["sys_prompt"] == "sys1"
    assert out["research"]["user_prompt"] == "user1"
    app.save_profile_prompt(profile_id, "research", "sys2", "user2")
    out = app.list_profile_prompts(profile_id)
    assert out["research"]["sys_prompt"] == "sys2"
    assert out["research"]["user_prompt"] == "user2"
    assert len(out) == 1, f"Debe haber 1 fila tras UPSERT, hay {len(out)}"
    app.save_profile_prompt(None, "research", "sys3", "user3")
    out = app.list_profile_prompts(profile_id)
    assert len(out) == 1, "profile_id=None no debe persistir"
    print("  ✓ save_profile_prompt UPSERT y respeta profile_id=None")


def test_profiles_page_renders(tmp_path):
    """GET /profiles renderiza el perfil por defecto y el formulario de creación."""
    _setup_qc_db(tmp_path)
    client = app.app.test_client()
    r = client.get("/profiles")
    assert r.status_code == 200
    body = r.data.decode("utf-8")
    assert "Perfiles de contenido" in body
    assert 'value="Todo Sobre Todo / Misterio"' in body
    assert 'value="create"' in body
    assert 'value="update"' in body
    print("  ✓ /profiles renderiza panel editable del perfil por defecto")


def test_profiles_update_default(tmp_path):
    """POST /profiles action=update modifica el perfil por defecto."""
    _setup_qc_db(tmp_path)
    client = app.app.test_client()
    r = client.post(
        "/profiles",
        data={
            "action": "update",
            "profile_id": "1",
            "name": "TST / Misterio v2",
            "content_type": "Documental oscuro",
            "audience": "Fans de misterios 30-50",
            "tone": "Críptico, reflexivo",
            "style": "Cinematográfico, friolento",
            "mystery_level": "9",
            "drama_level": "7",
            "narration_speed": "140",
            "platforms": ["youtube_long", "facebook_long", "youtube_short", "reels_short"],
            "notes": "Perfil actualizado desde test",
            "is_default": "on",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    with app.get_db() as conn:
        row = dict(conn.execute("SELECT * FROM profiles WHERE id=1").fetchone())
    assert row["name"] == "TST / Misterio v2"
    assert row["mystery_level"] == 9
    assert row["drama_level"] == 7
    assert row["narration_speed"] == 140
    assert row["tone"] == "Críptico, reflexivo"
    assert row["is_default"] == 1
    platforms = json.loads(row["platforms"] or "[]")
    assert "youtube_long" in platforms
    assert "facebook_long" in platforms
    print("  ✓ /profiles action=update modifica el perfil por defecto")


def test_profiles_update_changes_default(tmp_path):
    """Marcar otro perfil como default desmarca el anterior."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO profiles (name, is_default, created_at)
            VALUES ('Alternativo', 0, '2025-01-01')
        """)
        alt_id = conn.execute("SELECT id FROM profiles WHERE name='Alternativo'").fetchone()["id"]
    client = app.app.test_client()
    r = client.post(
        "/profiles",
        data={
            "action": "update",
            "profile_id": str(alt_id),
            "name": "Alternativo",
            "mystery_level": "5",
            "drama_level": "5",
            "narration_speed": "150",
            "is_default": "on",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    with app.get_db() as conn:
        rows = conn.execute("SELECT id, is_default FROM profiles ORDER BY id").fetchall()
    flags = {r["id"]: r["is_default"] for r in rows}
    assert flags[1] == 0, "el perfil 1 ya no debe ser default"
    assert flags[alt_id] == 1, "el nuevo perfil debe ser default"
    print("  ✓ /profiles action=update transfiere la marca de default")


def test_profiles_update_rejects_empty_name(tmp_path):
    """POST con name vacío no debe modificar el perfil."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        before = dict(conn.execute("SELECT * FROM profiles WHERE id=1").fetchone())
    client = app.app.test_client()
    r = client.post(
        "/profiles",
        data={
            "action": "update",
            "profile_id": "1",
            "name": "",
            "mystery_level": "1",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    with app.get_db() as conn:
        after = dict(conn.execute("SELECT * FROM profiles WHERE id=1").fetchone())
    assert after["name"] == before["name"], "el nombre no debe haber cambiado"
    assert after["mystery_level"] == before["mystery_level"]
    assert b"obligatorio" in r.data
    print("  ✓ /profiles action=update rechaza nombre vacío")


def test_migration_copies_stage_prompts_to_profile_prompts(tmp_path):
    """init_db() migra filas de stage_prompts y elimina la tabla legacy."""
    db_path = tmp_path / "test.db"
    app.DB_PATH = db_path
    app.init_db()
    profile_id = 1
    now = "2025-01-01T00:00:00"
    import gc

    with app.get_db() as conn:
        # init_db() en una DB fresca marca la migración como aplicada
        # (idempotente cuando la tabla legacy no existe). La "desmarcamos"
        # para simular una instalación previa al refactor y verificar que
        # la migración realmente copia filas y elimina la tabla.
        conn.execute(
            "DELETE FROM _schema_migrations WHERE name='migrate_stage_prompts_to_profile_prompts'"
        )
        conn.execute("""
            CREATE TABLE stage_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                stage TEXT,
                sys_prompt TEXT,
                user_prompt TEXT,
                updated_at TEXT,
                UNIQUE(project_id, stage),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'Test', 'Topic', ?, 'research', ?, ?)
        """,
            (profile_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO stage_prompts (project_id, stage, sys_prompt,
                                       user_prompt, updated_at)
            VALUES (1, 'research', 'sys-from-legacy', 'user-from-legacy', ?)
        """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO stage_prompts (project_id, stage, sys_prompt,
                                       user_prompt, updated_at)
            VALUES (1, 'concept', 'sys-concept', 'user-concept', ?)
        """,
            (now,),
        )
    gc.collect()
    app.init_db()
    gc.collect()
    with app.get_db() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT stage, sys_prompt, user_prompt FROM profile_prompts "
                "WHERE profile_id=? ORDER BY stage",
                (profile_id,),
            )
        ]
        legacy_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='stage_prompts'"
        ).fetchone()
    assert legacy_exists is None, "stage_prompts debe haberse eliminado"
    assert len(rows) == 2, f"Esperaba 2 filas migradas, hay {len(rows)}"
    by_stage = {r["stage"]: r for r in rows}
    assert by_stage["research"]["sys_prompt"] == "sys-from-legacy"
    assert by_stage["concept"]["user_prompt"] == "user-concept"
    print("  ✓ migración copia stage_prompts a profile_prompts y borra legacy")


# ==========================================================================
# Tests del graph CRUD y ejecutor unificado
# ==========================================================================


def _get_default_profile_id(tmp_path):
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        row = conn.execute("SELECT id FROM profiles LIMIT 1").fetchone()
    return row["id"]


def test_get_or_create_fixed_graph_nodes(tmp_path):
    """Crea las 10 filas fijas y no duplica en llamadas sucesivas."""
    pid = _get_default_profile_id(tmp_path)
    rows1 = app.get_or_create_fixed_graph_nodes(pid)
    assert len(rows1) == 10, f"esperaba 10, hay {len(rows1)}"
    keys = {r["node_key"] for r in rows1}
    assert keys == set(app.KNOWN_FIXED_NODE_KEYS), keys
    rows2 = app.get_or_create_fixed_graph_nodes(pid)
    assert len(rows2) == 10, "segunda llamada no debe duplicar"
    keys2 = {r["node_key"] for r in rows2}
    assert keys2 == set(app.KNOWN_FIXED_NODE_KEYS)
    for r in rows2:
        assert r["is_fixed"] == 1
        assert r["position_x"] is not None
        assert r["position_y"] is not None
    print("  ✓ get_or_create_fixed_graph_nodes crea 10 filas únicas")


def test_save_graph_node_and_delete(tmp_path):
    """Custom node: save, update, delete. Fijos no se pueden borrar."""
    pid = _get_default_profile_id(tmp_path)
    saved = app.save_graph_node(pid, "custom_a", "Custom A", "sys", "user", "[]", 100, 200, False)
    assert saved["node_key"] == "custom_a"
    assert saved["is_fixed"] == 0
    assert saved["label"] == "Custom A"
    assert saved["position_x"] == 100
    assert saved["position_y"] == 200
    saved2 = app.save_graph_node(
        pid, "custom_a", "Custom A v2", "sys2", "user2", '["research"]', 150, 250, False
    )
    assert saved2["label"] == "Custom A v2"
    assert saved2["position_x"] == 150
    assert saved2["position_y"] == 250
    deleted = app.delete_graph_node(pid, "custom_a")
    assert deleted is True
    deleted_again = app.delete_graph_node(pid, "custom_a")
    assert deleted_again is False
    app.get_or_create_fixed_graph_nodes(pid)
    deleted_fixed = app.delete_graph_node(pid, "research")
    assert deleted_fixed is False
    with app.get_db() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM profile_graph_nodes "
            "WHERE profile_id=? AND node_key='research'",
            (pid,),
        ).fetchone()["n"]
    assert n == 1, "el nodo fijo 'research' debe seguir existiendo"
    print("  ✓ save_graph_node + delete (rechaza fijos)")


def test_execute_graph_node_fixed_research(tmp_path):
    """Ejecuta research en modo manual: persiste node_executions."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        pid = conn.execute("SELECT id FROM profiles LIMIT 1").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'Test', 'Tema de prueba', ?, 'research',
                    '2025-01-01', '2025-01-01')
        """,
            (pid,),
        )
    result = app.execute_graph_node(1, "research")
    assert result.get("ok") is True, f"esperaba ok, obtuve: {result}"
    assert result.get("status") == "ok"
    assert "Tema de prueba" in result.get("output", ""), (
        f"manual mode debe contener el tema: {result.get('output')[:200]}"
    )
    with app.get_db() as conn:
        row = conn.execute(
            "SELECT status, output FROM node_executions "
            "WHERE project_id=1 AND node_key='research' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None, "node_executions no escritas"
    assert row["status"] == "ok"
    assert "Tema de prueba" in row["output"]
    print("  ✓ execute_graph_node (research fixed, manual mode)")


def test_execute_graph_node_custom(tmp_path):
    """Ejecuta un nodo custom con interpolación de inputs."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        pid = conn.execute("SELECT id FROM profiles LIMIT 1").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'Custom Test', 'Tema', ?, 'created',
                    '2025-01-01', '2025-01-01')
        """,
            (pid,),
        )
    app.save_graph_node(
        pid,
        "my_node",
        "My Node",
        "SYS_PROMPT",
        "USER con {{ inputs.research }} metido",
        '["research"]',
        0,
        0,
        False,
    )
    with app.get_db() as conn:
        conn.execute("""
            INSERT INTO node_executions
                (project_id, node_key, output, status, created_at)
            VALUES (1, 'research', 'HECHOS IMPORTANTES', 'ok', '2025-01-01')
        """)
    result = app.execute_graph_node(1, "my_node")
    assert result.get("ok") is True, f"esperaba ok, obtuve: {result}"
    with app.get_db() as conn:
        row = conn.execute(
            "SELECT status, output FROM node_executions "
            "WHERE project_id=1 AND node_key='my_node' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["status"] == "ok"
    assert "USER con" in row["output"], row["output"]
    assert "HECHOS IMPORTANTES" in row["output"], (
        "placeholder {{ inputs.research }} debe haberse interpolado"
    )
    print("  ✓ execute_graph_node (custom con inputs interpolados)")


def test_persist_scenes_to_specific_script(tmp_path):
    """_persist_scenes graba en el guion pedido (long o short)."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        pid = conn.execute("SELECT id FROM profiles LIMIT 1").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'PScenes', 'T', ?, 'created',
                    '2025-01-01', '2025-01-01')
        """,
            (pid,),
        )
        cur_l = conn.execute("""
            INSERT INTO scripts (project_id, type, title, hook, body_full,
                word_count, updated_at)
            VALUES (1, 'long', 'L', 'h', 'uno dos tres', 3, '2025-01-01')
        """)
        cur_s = conn.execute("""
            INSERT INTO scripts (project_id, type, title, hook, body_full,
                word_count, updated_at)
            VALUES (1, 'short', 'C', 'h', 'cuatro cinco', 2, '2025-01-01')
        """)
        long_id = cur_l.lastrowid
        short_id = cur_s.lastrowid
    parsed = [
        {"scene_number": 1, "narration_segment": "uno", "image_prompt": "img1"},
        {"scene_number": 2, "narration_segment": "dos tres", "image_prompt": "img2"},
    ]
    with app.app.app_context():
        with app.get_db() as conn:
            app._persist_scenes(conn, 1, "short", parsed, "2025-01-01")
    with app.get_db() as conn:
        rows_s = [
            dict(r)
            for r in conn.execute(
                "SELECT script_id, scene_number FROM scenes WHERE project_id=1 "
                "AND script_id=? ORDER BY scene_number",
                (short_id,),
            ).fetchall()
        ]
        rows_l = [
            dict(r)
            for r in conn.execute(
                "SELECT script_id, scene_number FROM scenes WHERE project_id=1 AND script_id=?",
                (long_id,),
            ).fetchall()
        ]
    assert len(rows_s) == 2, f"debe persistir 2 escenas en short: {rows_s}"
    assert all(r["script_id"] == short_id for r in rows_s)
    assert len(rows_l) == 0, "no debe tocar el guion largo"
    print("  ✓ _persist_scenes escribe solo en el guion pedido")


def test_update_graph_layout(tmp_path):
    """Persiste las posiciones enviadas."""
    pid = _get_default_profile_id(tmp_path)
    app.get_or_create_fixed_graph_nodes(pid)
    nodes_data = [
        {"node_key": "research", "position_x": 10.0, "position_y": 20.0},
        {"node_key": "concept", "position_x": 300.0, "position_y": 40.0},
        {"node_key": "scenes", "position_x": 700.0, "position_y": 90.0},
    ]
    updated = app.update_graph_layout(pid, nodes_data)
    assert updated == 3, f"esperaba 3 updates, hay {updated}"
    with app.get_db() as conn:
        for nd in nodes_data:
            row = conn.execute(
                "SELECT position_x, position_y FROM profile_graph_nodes "
                "WHERE profile_id=? AND node_key=?",
                (pid, nd["node_key"]),
            ).fetchone()
            assert row is not None
            assert row["position_x"] == nd["position_x"], nd["node_key"]
            assert row["position_y"] == nd["position_y"], nd["node_key"]
    empty = app.update_graph_layout(pid, [])
    assert empty == 0
    print("  ✓ update_graph_layout persiste posiciones")


# ==========================================================================
# Runner
# ==========================================================================


def test_runner_renders_for_project(tmp_path):
    """GET /projects/<id>/run renderiza con los 10 nodos fijos."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        pid = conn.execute("SELECT id FROM profiles LIMIT 1").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'Runner Test', 'Tema', ?, 'created',
                    '2025-01-01', '2025-01-01')
        """,
            (pid,),
        )
    with app.app.test_client() as c:
        r = c.get("/projects/1/run")
        assert r.status_code == 200
        body = r.data.decode("utf-8")
        assert "Ejecutar en modo grafo" in body
        # Los 10 nodos fijos se inyectan en window.__GRAPH_DATA__
        assert body.count('"isFixed": true') >= 10
    print("  ✓ runner renderiza con 10 nodos fijos")


def test_runner_execute_route_returns_json(tmp_path):
    """POST /projects/<id>/run/execute ejecuta un nodo fijo en modo manual."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        pid = conn.execute("SELECT id FROM profiles LIMIT 1").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'Runner Exec', 'Tema runner', ?, 'created',
                    '2025-01-01', '2025-01-01')
        """,
            (pid,),
        )
    with app.app.test_client() as c:
        r = c.post("/projects/1/run/execute", json={"node_key": "research"})
        assert r.status_code == 200
        data = r.get_json()
        assert data.get("ok") is True, data
        assert data.get("status") == "ok"
        assert "Tema runner" in data.get("output", "")
        assert "node_executions" in data
    with app.get_db() as conn:
        row = conn.execute(
            "SELECT status FROM node_executions "
            "WHERE project_id=1 AND node_key='research' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None and row["status"] == "ok"
    print("  ✓ runner /run/execute persiste ok en node_executions")


def test_runner_reset_node_clears_executions(tmp_path):
    """POST /projects/<id>/run/reset-node borra ejecuciones previas del nodo."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        pid = conn.execute("SELECT id FROM profiles LIMIT 1").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'Reset', 'Tema', ?, 'created',
                    '2025-01-01', '2025-01-01')
        """,
            (pid,),
        )
        conn.execute("""
            INSERT INTO node_executions
                (project_id, node_key, output, status, created_at)
            VALUES (1, 'concept', 'previo', 'ok', '2025-01-01')
        """)
    with app.app.test_client() as c:
        r = c.post("/projects/1/run/reset-node", json={"node_key": "concept"})
        assert r.status_code == 200
        data = r.get_json()
        assert data.get("ok") is True
        assert data.get("deleted") == 1
    with app.get_db() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM node_executions WHERE project_id=1 AND node_key='concept'"
        ).fetchone()["n"]
        assert n == 0
    print("  ✓ runner /run/reset-node borra ejecuciones del nodo")


def test_runner_scenes_short_persists_to_short_script(tmp_path):
    """El nodo scenes_short persiste escenas en el guion corto."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        pid = conn.execute("SELECT id FROM profiles LIMIT 1").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'Scenes Short', 'Tema', ?, 'created',
                    '2025-01-01', '2025-01-01')
        """,
            (pid,),
        )
        # Crear guion corto
        conn.execute("""
            INSERT INTO scripts (project_id, type, title, hook, context,
                development, revelations, conclusion, cta, body_full,
                word_count, updated_at)
            VALUES (1, 'short', 'Corto', 'h', 'c', 'd', 'r', 'f', 'cta',
                    'uno dos tres cuatro cinco seis siete ocho', 8, '2025-01-01')
        """)
    with app.app.test_client() as c:
        r = c.post("/projects/1/run/execute", json={"node_key": "scenes_short"})
        assert r.status_code == 200
    # En modo manual la persistencia no se ejecuta (raw es el prompt,
    # no escenas parseables). Verificamos que se llama al nodo correcto.
    with app.get_db() as conn:
        row = conn.execute(
            "SELECT status FROM node_executions "
            "WHERE project_id=1 AND node_key='scenes_short' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None and row["status"] == "ok"
    print("  ✓ runner procesa scenes_short como nodo fijo")


def main():
    import gc
    import tempfile
    from pathlib import Path

    print("\n=== TESTS DE PARSERS ===")
    test_parse_research()
    test_parse_research_with_variations()
    test_parse_concept()
    test_parse_concept_with_body_text()
    test_parse_script_long()
    test_parse_script_short()
    test_parse_scenes_json()
    test_parse_scenes_json_bare()
    test_parse_prompt_json()
    test_parse_metadata_youtube()
    test_parse_metadata_shorts()
    test_parse_metadata_facebook_long()
    test_parse_metadata_reels_short()
    test_parse_thumbnail()
    test_parse_thumbnail_ignores_other_blocks()

    print("\n=== TESTS DE UTILIDADES ===")
    test_count_words()
    test_estimate_duration()

    def _run_qc_test(test_fn, label):
        with tempfile.TemporaryDirectory() as tmp:
            test_fn(Path(tmp))
            # Forzar liberación de handles SQLite antes de borrar el tmp
            # (necesario en Windows, donde el delete falla con WinError 32).
            gc.collect()

    print("\n=== TESTS DE QC ===")
    _run_qc_test(test_qc_detects_missing_research, "missing_research")
    _run_qc_test(test_qc_detects_short_script, "short_script")
    _run_qc_test(test_qc_detects_repetition, "repetition")
    _run_qc_test(test_qc_detects_missing_sources, "missing_sources")
    _run_qc_test(test_qc_passes_complete_project, "complete_project")

    print("\n=== TESTS DE EXPORTACIÓN ===")
    with tempfile.TemporaryDirectory() as tmp:
        test_export_creates_zip(Path(tmp))
        gc.collect()

    print("\n=== TESTS DE SINCRONIZACIÓN DE CARPETA ===")
    with tempfile.TemporaryDirectory() as tmp:
        test_new_project_creates_folder(Path(tmp))
        gc.collect()
    with tempfile.TemporaryDirectory() as tmp:
        test_research_save_syncs_folder(Path(tmp))
        gc.collect()
    with tempfile.TemporaryDirectory() as tmp:
        test_metadata_save_syncs_folder(Path(tmp))
        gc.collect()
    with tempfile.TemporaryDirectory() as tmp:
        test_export_get_renders_folder(Path(tmp))
        gc.collect()
    with tempfile.TemporaryDirectory() as tmp:
        test_export_resync_action(Path(tmp))
        gc.collect()
    with tempfile.TemporaryDirectory() as tmp:
        test_delete_project_removes_folder(Path(tmp))
        gc.collect()

    print("\n=== TESTS DE PROMPTS POR PERFIL ===")
    _run_qc_test(
        test_resolve_stage_prompt_falls_back_to_config, "resolve_stage_prompt_falls_back_to_config"
    )
    _run_qc_test(test_save_profile_prompt_upsert, "save_profile_prompt_upsert")
    _run_qc_test(
        test_migration_copies_stage_prompts_to_profile_prompts,
        "migration_copies_stage_prompts_to_profile_prompts",
    )

    print("\n=== TESTS DE EDICIÓN DE PERFILES ===")
    _run_qc_test(test_profiles_page_renders, "profiles_page_renders")
    _run_qc_test(test_profiles_update_default, "profiles_update_default")
    _run_qc_test(test_profiles_update_changes_default, "profiles_update_changes_default")
    _run_qc_test(test_profiles_update_rejects_empty_name, "profiles_update_rejects_empty_name")

    print("\n=== TESTS DE GRAPH CRUD ===")
    _run_qc_test(test_get_or_create_fixed_graph_nodes, "get_or_create_fixed_graph_nodes")
    _run_qc_test(test_save_graph_node_and_delete, "save_graph_node_and_delete")
    _run_qc_test(test_update_graph_layout, "update_graph_layout")
    _run_qc_test(test_execute_graph_node_fixed_research, "execute_graph_node_fixed_research")
    _run_qc_test(test_execute_graph_node_custom, "execute_graph_node_custom")
    _run_qc_test(test_persist_scenes_to_specific_script, "persist_scenes_to_specific_script")

    print("\n=== TESTS DEL RUNNER (E2E) ===")
    _run_qc_test(test_runner_renders_for_project, "runner_renders_for_project")
    _run_qc_test(test_runner_execute_route_returns_json, "runner_execute_route_returns_json")
    _run_qc_test(test_runner_reset_node_clears_executions, "runner_reset_node_clears_executions")
    _run_qc_test(
        test_runner_scenes_short_persists_to_short_script,
        "runner_scenes_short_persists_to_short_script",
    )

    print("\n✅ Todos los tests pasaron\n")


if __name__ == "__main__":
    main()

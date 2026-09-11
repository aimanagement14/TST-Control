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
from services.templates import (
    RenderReport,
    render,
    render_profile,
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


def test_parse_metadata_youtube_long():
    text = """## TITULOS (5 opciones)
1. OVNIs: la verdad
2. Pentagon confirmado
3. UAPs al descubierto
4. Misterio en el cielo
5. LaPentagon contra los UAPs

## DESCRIPCION
Video sobre OVNIs en prosa continua. Se separa en párrafos.

## TAGS (15)
ovnis uap pentagono mil misterio aviadores

## CTA
Suscríbete al canal."""
    r = app.parse_metadata(text, "youtube_long")
    assert len(r["titles"]) == 5, f"titles: {r['titles']}"
    assert "Video sobre OVNIs" in r["description"]
    assert "ovnis" in r["tags"]
    assert "Suscríbete" in r["cta"]
    assert r["hashtags"] == [], "youtube_long no usa hashtags en el prompt nuevo"
    assert r["chapters"] == [], "youtube_long no usa capítulos en el prompt nuevo"
    print("  ✓ parse_metadata (youtube_long, dispatcher)")


def test_parse_metadata_youtube_short():
    text = """## TITULOS (3 opciones)
1. LaPentagon confirma OVNIs
2. UAPs en directo
3. Misterio sin resolver

## DESCRIPCION
Dos frases con gancho textual. Funciona sin audio.

## HASHTAGS (8-12)
#ovnis #uap #misterio #pentagono

## TAGS (10)
ovnis pentagono uap viral shorts

## CTA
Suscríbete y dale a la campana."""
    r = app.parse_metadata(text, "youtube_short")
    assert len(r["titles"]) == 3, f"titles: {r['titles']}"
    assert "Funciona sin audio" in r["description"]
    assert len(r["hashtags"]) == 4
    assert "Suscríbete" in r["cta"]
    assert r["caption"] == ""
    assert r["on_screen_text"] == []
    print("  ✓ parse_metadata (youtube_short, dispatcher)")


def test_parse_metadata_dispatcher_returns_canonical_shape():
    """Aunque el prompt no declare todos los campos, el dict siempre los trae."""
    r = app.parse_metadata("## DESCRIPCION\nSolo descripción.", "facebook_long")
    for key in (
        "titles",
        "description",
        "chapters",
        "tags",
        "hashtags",
        "caption",
        "hook",
        "cta",
        "on_screen_text",
    ):
        assert key in r, f"Falta clave canónica {key} en respuesta de facebook_long"
    assert r["titles"] == []
    assert r["on_screen_text"] == []
    assert "Solo descripción" in r["description"]
    print("  ✓ parse_metadata (dispatcher devuelve forma canónica completa)")


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
    """Al crear un proyecto, la carpeta se sincroniza con el contrato nuevo."""
    _setup_qc_db(tmp_path)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        c = app.app.test_client()
        r = c.post(
            "/projects/new",
            data={
                "name": "Carpeta auto",
                "topic": "verifico la sincronización",
                "profile_id": "1",
            },
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
        stage_files = sorted(folder.glob("stage_*.md"))
        assert len(stage_files) == 7, (
            f"esperaba 7 stage_<id>.md, hay {len(stage_files)}: {stage_files}"
        )
        assert (folder / "08_paquete_completo.json").exists()
        legacy_dirs = ["03_guiones", "04_escenas", "05_metadata", "06_thumbnails"]
        for d in legacy_dirs:
            assert not (folder / d).exists(), (
                f"carpeta legacy {d} no debe existir en el modelo nuevo"
            )
        print("  ✓ crear proyecto sincroniza la carpeta con stage_<id>.md")
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


def test_project_video_lifecycle(tmp_path):
    """Los videos se pueden añadir, usar y quitar con sus datos asociados."""
    _setup_qc_db(tmp_path)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        with app.get_db() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, topic, status, created_at, updated_at)
                VALUES (1, 'Videos Test', 'Tema', 'research', '2025-01-01', '2025-01-01')
                """
            )
        app.ensure_default_project_videos(1)
        client = app.app.test_client()
        page = client.get("/projects/1")
        assert page.status_code == 200
        assert "Videos del proyecto" in page.data.decode("utf-8")
        assert "Añadir video" in page.data.decode("utf-8")

        response = client.post(
            "/projects/1/videos",
            data={"action": "add", "name": "Video extra", "script_type": "short"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.get_db() as conn:
            video = conn.execute(
                "SELECT * FROM videos WHERE project_id=1 AND name='Video extra'"
            ).fetchone()
            assert video is not None
            video_id = video["id"]

        response = client.post(
            "/projects/1/scripts",
            data={
                "action": "save",
                "video_id": str(video_id),
                "text": "## TITULO\nExtra\n\n## HOOK\nGancho\n\n## CTA\nSuscríbete",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        scripts_page = client.get(f"/projects/1/scripts?video_id={video_id}")
        assert scripts_page.status_code == 200
        assert "Video extra" in scripts_page.data.decode("utf-8")
        with app.get_db() as conn:
            script = conn.execute(
                "SELECT * FROM scripts WHERE video_id=?", (video_id,)
            ).fetchone()
            assert script is not None
            script_id = script["id"]

        response = client.post(
            "/projects/1/scenes",
            data={
                "action": "save",
                "video_id": str(video_id),
                "text": "ESCENA 1\nTEXTO AUDIO: Extra\nIMAGEN: Imagen extra",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        scenes_page = client.get(f"/projects/1/scenes?video_id={video_id}")
        assert scenes_page.status_code == 200
        assert "Video extra" in scenes_page.data.decode("utf-8")
        response = client.post(
            "/projects/1/metadata",
            data={
                "action": "save",
                "video_id": str(video_id),
                "platform": "youtube_short",
                "script_id": str(script_id),
                "text": "## TITULOS\n1. Extra\n\n## DESCRIPCION\nDescripción extra",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        response = client.post(
            "/projects/1/thumbnails",
            data={
                "action": "save",
                "video_id": str(video_id),
                "script_id": str(script_id),
                "text": "## MINIATURA\nPrompt extra",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        metadata_page = client.get(f"/projects/1/metadata?video_id={video_id}")
        assert metadata_page.status_code == 200
        assert "Video extra" in metadata_page.data.decode("utf-8")
        thumbnails_page = client.get(f"/projects/1/thumbnails?video_id={video_id}")
        assert thumbnails_page.status_code == 200
        assert "Video extra" in thumbnails_page.data.decode("utf-8")
        with app.get_db() as conn:
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM scenes WHERE script_id=?", (script_id,)
            ).fetchone()["n"] == 1
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM metadata_records WHERE video_id=?",
                (video_id,),
            ).fetchone()["n"] == 1
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM thumbnail_records WHERE video_id=?",
                (video_id,),
            ).fetchone()["n"] == 1

        response = client.post(
            "/projects/1/videos",
            data={"action": "delete", "video_id": str(video_id)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        page = client.get("/projects/1")
        assert page.status_code == 200
        with app.get_db() as conn:
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM videos WHERE id=?", (video_id,)
            ).fetchone()["n"] == 0
            long_video = conn.execute(
                "SELECT id FROM videos WHERE project_id=1 AND key='long'"
            ).fetchone()
        response = client.post(
            "/projects/1/videos",
            data={"action": "delete", "video_id": str(long_video["id"])},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.get_db() as conn:
            short_video = conn.execute(
                "SELECT id FROM videos WHERE project_id=1 AND key='short'"
            ).fetchone()
        response = client.post(
            "/projects/1/videos",
            data={"action": "delete", "video_id": str(short_video["id"])},
            follow_redirects=False,
        )
        assert response.status_code == 302
        page = client.get("/projects/1")
        assert "Añadir video" in page.data.decode("utf-8")
        app.init_db()
        with app.get_db() as conn:
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM videos WHERE key='long' AND project_id=1"
            ).fetchone()["n"] == 0
            assert conn.execute("SELECT COUNT(*) AS n FROM videos WHERE id=?", (video_id,)).fetchone()["n"] == 0
            assert conn.execute("SELECT COUNT(*) AS n FROM scripts WHERE video_id=?", (video_id,)).fetchone()["n"] == 0
            assert conn.execute("SELECT COUNT(*) AS n FROM metadata_records WHERE video_id=?", (video_id,)).fetchone()["n"] == 0
            assert conn.execute("SELECT COUNT(*) AS n FROM thumbnail_records WHERE video_id=?", (video_id,)).fetchone()["n"] == 0
        print("  ✓ ciclo de vida de videos del proyecto")
    finally:
        app.PROJECTS_DIR = original


# ==========================================================================
# Tests de prompts por perfil (graph foundation)
# ==========================================================================


def test_resolve_stage_prompt_falls_back_to_config(tmp_path):
    """Sin fila en profile_prompts, devuelve los strings de CONFIG (renderizados)."""
    _setup_qc_db(tmp_path)
    profile_id = 1
    sys_p, user_p = app.resolve_stage_prompt(profile_id, "research")
    raw_sys = app.CONFIG["prompts"]["research"]["system"]
    raw_user = app.CONFIG["prompts"]["research"]["format"]
    expected_sys, _ = render_profile(raw_sys, app.get_profile(profile_id))
    expected_user, _ = render_profile(raw_user, app.get_profile(profile_id))
    assert sys_p == expected_sys, "SYS renderizado difiere de raw CONFIG"
    assert user_p == expected_user, "USER renderizado difiere de raw CONFIG"
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


# ==========================================================================
# Fase 1.3: mini-motor de plantillas + inyección de perfil
# ==========================================================================


def test_render_substitutes_known_paths():
    """render sustituye {{path.to.value}} y reporta unknown en el report."""
    text, report = render(
        "Canal={{app.name}} misterio={{profile.mystery_level}} tono={{profile.tone}}",
        {
            "app": {"name": "Todo Sobre Todo"},
            "profile": {"mystery_level": 7, "tone": "serio"},
        },
    )
    assert text == "Canal=Todo Sobre Todo misterio=7 tono=serio"
    assert isinstance(report, RenderReport)
    assert report.unknown == set()
    print("  ✓ render sustituye paths conocidos")


def test_render_reports_unknown_paths():
    """render sustituye paths desconocidos por cadena vacía y los reporta."""
    text, report = render(
        "Hola {{profile.x}} y {{profile.y}} misterioso={{profile.mystery_level}}",
        {"profile": {"mystery_level": 8}},
    )
    assert text == "Hola  y  misterioso=8"
    assert report.unknown == {"profile.x", "profile.y"}
    print("  ✓ render reporta paths desconocidos")


def test_render_profile_normalizes_platforms_csv():
    """render_profile construye el contexto con platforms_csv legible."""
    text, _ = render_profile(
        "Plataformas: {{profile.platforms_csv}}",
        {"platforms": '["youtube", "shorts", "facebook"]'},
    )
    assert text == "Plataformas: youtube, shorts, facebook"
    print("  ✓ render_profile serializa platforms como CSV")


def test_resolve_stage_prompt_renders_profile_template(tmp_path):
    """SYS con {{profile.*}} se renderiza contra el perfil activo."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO profile_prompts "
            "(profile_id, stage, sys_prompt, user_prompt, updated_at) "
            "VALUES (1, 'research', ?, ?, '2025-01-01')",
            (
                "Canal: {{app.name}}. Misterio: {{profile.mystery_level}}/10.",
                "Tono: {{profile.tone}}",
            ),
        )
        conn.execute(
            "UPDATE profiles SET mystery_level=8, tone='oscuro y solemne' WHERE id=1"
        )
    sys_p, user_p = app.resolve_stage_prompt(1, "research")
    assert "Canal: Todo Sobre Todo." in sys_p
    assert "Misterio: 8/10." in sys_p
    assert user_p == "Tono: oscuro y solemne"
    print("  ✓ resolve_stage_prompt aplica el motor de plantillas contra el perfil")


def test_resolve_stage_prompt_aliases(tmp_path):
    """Aliases del runner (scenes_short → scenes, scripts → script_long, thumbnails → thumbnail_long)."""
    _setup_qc_db(tmp_path)
    sys_short_alias, _ = app.resolve_stage_prompt(1, "scenes_short")
    sys_canonical, _ = app.resolve_stage_prompt(1, "scenes")
    assert sys_short_alias == sys_canonical

    sys_scripts_alias, _ = app.resolve_stage_prompt(1, "scripts")
    sys_long, _ = app.resolve_stage_prompt(1, "script_long")
    assert sys_scripts_alias == sys_long

    sys_thumbs_alias, _ = app.resolve_stage_prompt(1, "thumbnails")
    sys_thumb_long, _ = app.resolve_stage_prompt(1, "thumbnail_long")
    assert sys_thumbs_alias == sys_thumb_long
    print("  ✓ resolve_stage_prompt respeta aliases scenes_short/scripts/thumbnails")


def test_roadmap_instruction_finds_row_by_roadmap_name(tmp_path):
    """_roadmap_instruction_for prioriza la key del roadmap sobre la de CONFIG."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO profile_prompts "
            "(profile_id, stage, sys_prompt, user_prompt, updated_at) "
            "VALUES (1, 'scripts', 'CUSTOM_SYS', 'CUSTOM_USER', '2025-01-01')"
        )
        conn.commit()
    with app.get_db() as conn:
        text = app._roadmap_instruction_for(conn, profile_id=1, stage_name="scripts")
    assert "CUSTOM_SYS" in text and "CUSTOM_USER" in text
    print("  ✓ _roadmap_instruction_for encuentra la fila por nombre de roadmap")


def test_config_has_no_orphan_legacy_keys():
    """Config.json ya no contiene metadata_youtube ni metadata_shorts (Fase 1.1)."""
    keys = set(app.CONFIG["prompts"].keys())
    assert "metadata_youtube" not in keys, "metadata_youtube es código muerto"
    assert "metadata_shorts" not in keys, "metadata_shorts es código muerto"
    expected = {
        "research",
        "concept",
        "script_long",
        "script_short",
        "scenes",
        "metadata_youtube_long",
        "metadata_facebook_long",
        "metadata_youtube_short",
        "metadata_reels_short",
        "thumbnail_long",
        "thumbnail_short",
    }
    missing = expected - keys
    assert not missing, f"Faltan keys esperadas en config.json: {missing}"
    print("  ✓ config.json sin huérfanos y con todas las keys esperadas")


# ==========================================================================
# Fase 4: prompt refiner post-QC
# ==========================================================================


def test_build_refiner_prompt_includes_issues():
    """El user_msg del refiner incluye cada issue con stage y severity."""
    issues = [
        ("scripts", "warning", "Palabra repetida 3x: «misterio»", "long", 1),
        ("scenes", "info", "Solo 5 escenas en short", "short", 2),
    ]
    _, user_msg = app.build_refiner_prompt(
        profile={"tone": "serio", "mystery_level": 7},
        stage_label="scripts",
        current_output="# Guion\nTexto...",
        issues=issues,
        original_format="## TITULO\n[...]\n## HOOK\n[...]",
    )
    assert "Etapa a refinar: scripts" in user_msg
    assert "[warning] scripts" in user_msg
    assert "[info] scenes" in user_msg
    assert "Palabra repetida" in user_msg
    assert "Solo 5 escenas" in user_msg
    assert "# Guion" in user_msg
    print("  ✓ build_refiner_prompt inyecta la lista de issues en el user_msg")


def test_build_refiner_prompt_respects_original_format():
    """El refiner conserva el bloque FORMAT del prompt original en su user_msg."""
    fmt = "## TITULOS (5 opciones)\n1. [título]\n## DESCRIPCION\n[...]"
    _, user_msg = app.build_refiner_prompt(
        profile=None,
        stage_label="metadata_youtube_long",
        current_output="output",
        issues=[],
        original_format=fmt,
    )
    assert "TITULOS (5 opciones)" in user_msg
    assert "## DESCRIPCION" in user_msg
    print("  ✓ build_refiner_prompt respeta el FORMAT del prompt original")


def test_config_visual_style_keywords_is_shared():
    """Solo hay UNA lista canónica de keywords visuales en CONFIG."""
    ks = app.CONFIG.get("visual_style", {}).get("keywords")
    assert ks, "Falta visual_style.keywords en CONFIG"
    expected_count = 14
    items = [s.strip() for s in ks.split(",")]
    assert len(items) == expected_count, f"keywords tiene {len(items)} items, esperaba {expected_count}"
    for must in ["Cinematic Hyperrealism", "Orange & Teal Color Grading", "Documentary Premium Quality"]:
        assert must in items, f"Falta keyword obligatoria: {must}"
    print("  ✓ visual_style.keywords centraliza las 14 keywords visuales")


def test_visual_prompts_reference_shared_keyword_token():
    """Los prompts visuales referencian {{app.visual_style_keywords}}, no lista literal."""
    for stage in ("scenes", "thumbnail_long", "thumbnail_short"):
        sys_text = app.CONFIG["prompts"][stage]["system"]
        fmt_text = app.CONFIG["prompts"][stage]["format"]
        assert "{{app.visual_style_keywords}}" in sys_text or "{{app.visual_style_keywords}}" in fmt_text, (
            f"{stage} no usa la variable compartida"
        )
        canon = app.CONFIG["visual_style"]["keywords"]
        full_list = canon in sys_text or canon in fmt_text
        assert not full_list, f"{stage} todavía tiene la lista literal completa hardcoded"
    print("  ✓ scenes / thumbnail_* usan la variable en lugar de la lista literal")



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
# Tests del modelo genérico de hoja de ruta (roadmap + project_stages)
# ==========================================================================


def test_default_profile_seeds_seven_roadmap_stages(tmp_path):
    """init_db() siembra las 7 etapas base del perfil por defecto."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        rows = conn.execute(
            "SELECT name, sort_order, is_active FROM roadmap_stages "
            "WHERE profile_id=1 ORDER BY sort_order, id"
        ).fetchall()
    assert len(rows) == 7, f"esperaba 7, hay {len(rows)}: {[r['name'] for r in rows]}"
    names = [r["name"] for r in rows]
    assert names == list(app.DEFAULT_ROADMAP_STAGES), names
    assert all(r["is_active"] == 1 for r in rows)
    sort_orders = [r["sort_order"] for r in rows]
    assert sort_orders == list(range(7)), sort_orders
    print("  ✓ perfil por defecto siembra 7 roadmap_stages activos en orden")


def test_new_profile_seeds_seven_roadmap_stages(tmp_path):
    """POST /profiles action=create siembra las 7 etapas en el nuevo perfil."""
    _setup_qc_db(tmp_path)
    client = app.app.test_client()
    r = client.post(
        "/profiles",
        data={
            "action": "create",
            "name": "Perfil test",
            "content_type": "Docu",
            "audience": "x",
            "tone": "serio",
            "style": "cinema",
            "notes": "",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    with app.get_db() as conn:
        pid = conn.execute(
            "SELECT id FROM profiles WHERE name='Perfil test'"
        ).fetchone()["id"]
        names = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM roadmap_stages WHERE profile_id=? ORDER BY sort_order",
                (pid,),
            ).fetchall()
        ]
    assert names == list(app.DEFAULT_ROADMAP_STAGES), names
    print("  ✓ crear perfil siembra 7 roadmap_stages con los nombres por defecto")


def test_new_project_seeds_seven_project_stages(tmp_path):
    """Crear un proyecto siembra 7 project_stages, uno por roadmap_stage activa."""
    _setup_qc_db(tmp_path)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        c = app.app.test_client()
        r = c.post(
            "/projects/new",
            data={"name": "P1", "topic": "tema", "profile_id": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        with app.get_db() as conn:
            pid = conn.execute(
                "SELECT id FROM projects WHERE name='P1'"
            ).fetchone()["id"]
            stages = conn.execute(
                """
                SELECT ps.id AS ps_id, rs.name, rs.sort_order,
                       ps.instruction, ps.response
                FROM project_stages ps
                JOIN roadmap_stages rs ON rs.id = ps.roadmap_stage_id
                WHERE ps.project_id = ?
                ORDER BY rs.sort_order, rs.id
                """,
                (pid,),
            ).fetchall()
        assert len(stages) == 7, f"esperaba 7 project_stages, hay {len(stages)}"
        names = [s["name"] for s in stages]
        assert names == list(app.DEFAULT_ROADMAP_STAGES), names
        with_response = [s for s in stages if (s["response"] or "").strip()]
        assert len(with_response) == 0, (
            f"las project_stages nuevas deben tener response vacía: {with_response}"
        )
        for s in stages:
            if s["name"] == "qc":
                continue
            assert (s["instruction"] or "").strip(), (
                f"project_stage '{s['name']}' debe traer instruction inicial"
            )
        print("  ✓ crear proyecto siembra 7 project_stages (qc sin instrucción por contrato)")
    finally:
        app.PROJECTS_DIR = original


def test_project_stage_get_renders(tmp_path):
    """GET /projects/<id>/stages/<stage_id> renderiza la etapa."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'P', 'tema', 1, 'research',
                    '2025-01-01', '2025-01-01')
        """
        )
    app.sync_project_stages_for_project(1)
    with app.get_db() as conn:
        sid = conn.execute(
            "SELECT id FROM project_stages WHERE project_id=1 ORDER BY id LIMIT 1"
        ).fetchone()["id"]
    with app.app.test_client() as c:
        r = c.get(f"/projects/1/stages/{sid}")
        assert r.status_code == 200, r.status_code
        body = r.data.decode("utf-8")
        assert "Instrucción" in body
        assert "Respuesta" in body
        assert "Guardar" in body
        assert "Etapas del proyecto" in body
    print("  ✓ GET /projects/<id>/stages/<stage_id> renderiza la etapa")


def test_project_stage_post_saves_instruction_and_response(tmp_path):
    """POST /projects/<id>/stages/<stage_id> action=save guarda instruction y response."""
    _setup_qc_db(tmp_path)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        with app.get_db() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, topic, profile_id, status,
                                      created_at, updated_at)
                VALUES (1, 'P', 'tema', 1, 'research',
                        '2025-01-01', '2025-01-01')
            """
            )
        app.sync_project_stages_for_project(1)
        with app.get_db() as conn:
            sid = conn.execute(
                "SELECT id FROM project_stages WHERE project_id=1 ORDER BY id LIMIT 1"
            ).fetchone()["id"]
        with app.app.test_client() as c:
            r = c.post(
                f"/projects/1/stages/{sid}",
                data={
                    "action": "save",
                    "instruction": "instr editada",
                    "response": "respuesta guardada",
                },
                follow_redirects=False,
            )
            assert r.status_code == 302, r.status_code
        with app.get_db() as conn:
            row = dict(
                conn.execute(
                    "SELECT instruction, response FROM project_stages WHERE id=?",
                    (sid,),
                ).fetchone()
            )
        assert row["instruction"] == "instr editada", row
        assert row["response"] == "respuesta guardada", row
        stage_file = app.safe_project_dir(1, "P") / f"stage_{sid}.md"
        assert stage_file.exists(), f"falta {stage_file}"
        content = stage_file.read_text(encoding="utf-8")
        assert "instr editada" in content
        assert "respuesta guardada" in content
        print("  ✓ POST /stages/<id> action=save guarda y reescribe stage_<id>.md")
    finally:
        app.PROJECTS_DIR = original


def test_non_empty_response_marks_stage_done(tmp_path):
    """Una respuesta no vacía en project_stages marca la etapa como hecha."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'P', 'tema', 1, 'research',
                    '2025-01-01', '2025-01-01')
        """
        )
    app.sync_project_stages_for_project(1)
    with app.get_db() as conn:
        row = conn.execute(
            "SELECT id, roadmap_stage_id FROM project_stages "
            "WHERE project_id=1 ORDER BY id LIMIT 1"
        ).fetchone()
        sid = row["id"]
        rs_id = row["roadmap_stage_id"]
        rs_name = conn.execute(
            "SELECT name FROM roadmap_stages WHERE id=?", (rs_id,)
        ).fetchone()["name"]
    project = {"id": 1}
    before = app.project_stage_status(project)
    assert before.get(rs_name) is False, f"debe empezar sin hacer: {before}"
    with app.get_db() as conn:
        conn.execute(
            "UPDATE project_stages SET response='contenido real' WHERE id=?", (sid,)
        )
    after = app.project_stage_status(project)
    assert after.get(rs_name) is True, f"esperaba True tras guardar: {after}"
    print("  ✓ respuesta no vacía marca la etapa como hecha en project_stage_status")


# ==========================================================================
# Tests de estado por video (stepper y Hoja de ruta)
# ==========================================================================


def test_video_stage_status_per_video_breakdown(tmp_path):
    """``video_stage_status`` devuelve el estado de cada etapa por video."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'P', 'tema', 1, 'research',
                    '2025-01-01', '2025-01-01')
        """
            )
    app.sync_project_stages_for_project(1)
    app.ensure_default_project_videos(1)
    with app.get_db() as conn:
        long_video = conn.execute(
            "SELECT id FROM videos WHERE project_id=1 AND key='long'"
        ).fetchone()
        long_id = long_video["id"]
        short_video = conn.execute(
            "SELECT id FROM videos WHERE project_id=1 AND key='short'"
        ).fetchone()
        short_id = short_video["id"]
        conn.execute(
            """
            INSERT INTO scripts (project_id, video_id, type, title, hook, body_full,
                word_count, updated_at)
            VALUES (1, ?, 'long', 'T', 'h',
                'palabra1 palabra2 palabra3', 3, '2025-01-01')
            """,
            (long_id,),
        )

    from services.stages import video_stage_status
    state = video_stage_status(1)
    assert [v["key"] for v in state] == ["long", "short"], state
    long_state = next(v for v in state if v["key"] == "long")
    short_state = next(v for v in state if v["key"] == "short")
    assert long_state["stages"]["scripts"] is True
    assert short_state["stages"]["scripts"] is False
    assert long_state["stages"]["scenes"] is False
    assert long_state["stages"]["metadata"] is False
    assert short_state["id"] == short_id
    print("  ✓ video_stage_status expone scripts/escenas/metadata/qc por video")


def test_project_stage_status_aggregates_per_video(tmp_path):
    """``project_stage_status`` agrega por video: si uno no está listo, la etapa no lo está."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'P', 'tema', 1, 'research',
                    '2025-01-01', '2025-01-01')
        """
            )
    app.sync_project_stages_for_project(1)
    app.ensure_default_project_videos(1)
    with app.get_db() as conn:
        long_id = conn.execute(
            "SELECT id FROM videos WHERE project_id=1 AND key='long'"
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO scripts (project_id, video_id, type, title, hook, body_full,
                word_count, updated_at)
            VALUES (1, ?, 'long', 'T', 'h',
                'palabra1 palabra2 palabra3', 3, '2025-01-01')
            """,
            (long_id,),
        )

    project = {"id": 1}
    status = app.project_stage_status(project)
    assert status["scripts"] is False, f"short sin guion → scripts False: {status}"
    assert status["scenes"] is False
    assert status["metadata"] is False
    assert status["thumbnails"] is False

    with app.get_db() as conn:
        short_id = conn.execute(
            "SELECT id FROM videos WHERE project_id=1 AND key='short'"
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO scripts (project_id, video_id, type, title, hook, body_full,
                word_count, updated_at)
            VALUES (1, ?, 'short', 'T2', 'h',
                'palabra1 palabra2 palabra3', 3, '2025-01-01')
            """,
            (short_id,),
        )

    status = app.project_stage_status(project)
    assert status["scripts"] is True, f"ambos con guion → scripts True: {status}"
    print("  ✓ project_stage_status agrega etapas per-video (todos los videos)")


def test_qc_state_pending_analyzed_skipped(tmp_path):
    """qc_state distingue pendiente, analizado y saltado para el QC per-video."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'P', 'tema', 1, 'research',
                    '2025-01-01', '2025-01-01')
        """
            )
    app.sync_project_stages_for_project(1)
    app.ensure_default_project_videos(1)
    with app.get_db() as conn:
        long_id = conn.execute(
            "SELECT id FROM videos WHERE project_id=1 AND key='long'"
        ).fetchone()["id"]

    from services.stages import video_stage_status

    pending = video_stage_status(1)
    assert len(pending) == 2
    assert all(v["stages"]["qc"] is False for v in pending), pending

    with app.get_db() as conn:
        conn.execute(
            """
            INSERT INTO qc_issues (project_id, stage, severity, message, field,
                video_id, created_at)
            VALUES (1, 'scripts', 'error', 'Falta el guion de Video 5 min', 'long',
                ?, '2025-01-01')
            """,
            (long_id,),
        )
        conn.execute(
            "UPDATE projects SET qc_state='analyzed' WHERE id=1"
        )

    state = video_stage_status(1)
    long_state = next(v for v in state if v["key"] == "long")
    short_state = next(v for v in state if v["key"] == "short")
    assert long_state["stages"]["qc"] is False, "long con error debe ser False"
    assert short_state["stages"]["qc"] is True, "short sin error debe ser True"

    with app.get_db() as conn:
        conn.execute("DELETE FROM qc_issues WHERE project_id=1")
        conn.execute("UPDATE projects SET qc_state='skipped' WHERE id=1")

    state = video_stage_status(1)
    assert all(v["stages"]["qc"] is True for v in state), state
    print("  ✓ QC per-video: pendiente, analizado, saltado")


def test_pipeline_view_exposes_per_video_breakdown(tmp_path):
    """``pipeline_view`` adjunta ``videos`` en cada etapa per-video."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'P', 'tema', 1, 'research',
                    '2025-01-01', '2025-01-01')
        """
            )
    app.sync_project_stages_for_project(1)
    app.ensure_default_project_videos(1)

    client = app.app.test_client()
    client.get("/projects/1")
    with app.app.test_request_context():
        view = app.pipeline_view({"id": 1, "profile_id": 1})
    scripts_cell = next(c for c in view["cells"] if c["key"] == "scripts")
    research_cell = next(c for c in view["cells"] if c["key"] == "research")
    assert scripts_cell["per_video"] is True, scripts_cell
    assert scripts_cell["videos_total"] == 2, scripts_cell
    assert scripts_cell["videos_done"] == 0
    assert all(v["stage_key"] == "scripts" for v in scripts_cell["videos"])
    assert research_cell["per_video"] is False
    assert research_cell["videos_total"] == 0
    print("  ✓ pipeline_view expone desglose per-video en Guiones/Escenas/etc.")


def test_update_stage_renames_reorders_activates_deactivates(tmp_path):
    """POST /profiles action=update_stage renombra, reordena, activa y desactiva."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        sid = conn.execute(
            "SELECT id FROM roadmap_stages WHERE profile_id=1 ORDER BY sort_order LIMIT 1"
        ).fetchone()["id"]
    client = app.app.test_client()
    r = client.post(
        "/profiles",
        data={
            "action": "update_stage",
            "profile_id": "1",
            "stage_id": str(sid),
            "name": "Etapa renombrada",
            "order": "5",
            "instruction": "instr nueva",
            "active": "on",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    with app.get_db() as conn:
        row = dict(
            conn.execute(
                "SELECT name, sort_order, is_active, instruction FROM roadmap_stages "
                "WHERE id=?",
                (sid,),
            ).fetchone()
        )
    assert row["name"] == "Etapa renombrada", row
    assert row["sort_order"] == 5, row
    assert row["is_active"] == 1, row
    assert row["instruction"] == "instr nueva", row

    r = client.post(
        "/profiles",
        data={
            "action": "update_stage",
            "profile_id": "1",
            "stage_id": str(sid),
            "name": "Etapa renombrada",
            "order": "5",
            "instruction": "instr nueva",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    with app.get_db() as conn:
        is_active = conn.execute(
            "SELECT is_active FROM roadmap_stages WHERE id=?", (sid,)
        ).fetchone()["is_active"]
    assert is_active == 0, "debe haberse desactivado al omitir 'active'"
    print("  ✓ /profiles update_stage renombra, reordena, activa y desactiva")


def test_delete_stage_cascades_project_stages(tmp_path):
    """Borrar una roadmap_stage hace CASCADE en sus project_stages."""
    _setup_qc_db(tmp_path)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        with app.get_db() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, topic, profile_id, status,
                                      created_at, updated_at)
                VALUES (1, 'P', 'tema', 1, 'research',
                        '2025-01-01', '2025-01-01')
            """
            )
        app.sync_project_stages_for_project(1)
        with app.get_db() as conn:
            sid = conn.execute(
                "SELECT id FROM roadmap_stages WHERE profile_id=1 ORDER BY sort_order LIMIT 1"
            ).fetchone()["id"]
            n_before = conn.execute(
                "SELECT COUNT(*) AS n FROM project_stages WHERE roadmap_stage_id=?",
                (sid,),
            ).fetchone()["n"]
        assert n_before == 1, f"esperaba 1 project_stage antes, hay {n_before}"
        with app.app.test_client() as c:
            r = c.post(
                "/profiles",
                data={
                    "action": "delete_stage",
                    "profile_id": "1",
                    "stage_id": str(sid),
                },
                follow_redirects=True,
            )
            assert r.status_code == 200
        with app.get_db() as conn:
            n_after = conn.execute(
                "SELECT COUNT(*) AS n FROM project_stages WHERE roadmap_stage_id=?",
                (sid,),
            ).fetchone()["n"]
            rs_exists = conn.execute(
                "SELECT 1 FROM roadmap_stages WHERE id=?", (sid,)
            ).fetchone()
        assert n_after == 0, f"esperaba 0 tras CASCADE, hay {n_after}"
        assert rs_exists is None, "la roadmap_stage debe haberse eliminado"
        print("  ✓ delete_stage hace CASCADE en project_stages")
    finally:
        app.PROJECTS_DIR = original


def test_migration_backfills_legacy_content_into_project_stages(tmp_path):
    """init_db() migra contenido legacy de research/concept/etc a project_stages."""
    db_path = tmp_path / "test.db"
    app.DB_PATH = db_path
    app.init_db()
    now = "2025-01-01T00:00:00"
    import gc

    with app.get_db() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'Legacy', 'Tema', 1, 'research', ?, ?)
            """,
            (now, now),
        )
        conn.execute(
            "DELETE FROM _schema_migrations WHERE name='migrate_to_roadmap_model'"
        )
        conn.execute("DELETE FROM roadmap_stages")
        conn.execute("DELETE FROM project_stages")
        conn.execute(
            """
            INSERT INTO research (project_id, content, sources, updated_at)
            VALUES (1, 'investigación vieja con detalle', '["a","b","c"]', ?)
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO concept (project_id, angle, thesis, updated_at)
            VALUES (1, 'ángulo viejo', 'tesis vieja', ?)
            """,
            (now,),
        )
    gc.collect()
    app.init_db()
    gc.collect()
    with app.get_db() as conn:
        stages = conn.execute(
            """
            SELECT rs.name, ps.response FROM project_stages ps
            JOIN roadmap_stages rs ON rs.id = ps.roadmap_stage_id
            WHERE ps.project_id = 1
            ORDER BY rs.sort_order
            """
        ).fetchall()
    by_name = {s["name"]: (s["response"] or "") for s in stages}
    assert "investigación vieja" in by_name["research"], by_name["research"]
    assert "ángulo viejo" in by_name["concept"], by_name["concept"]
    print("  ✓ migración backfilea contenido legacy en project_stages")


def test_stage_file_uses_stable_roadmap_id(tmp_path):
    """El nombre del archivo usa el id de roadmap_stage, no el nombre."""
    _setup_qc_db(tmp_path)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        with app.get_db() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, topic, profile_id, status,
                                      created_at, updated_at)
                VALUES (1, 'P', 'tema', 1, 'research',
                        '2025-01-01', '2025-01-01')
            """
            )
        app.sync_project_stages_for_project(1)
        app.sync_project_folder(1)
        folder = app.safe_project_dir(1, "P")
        with app.get_db() as conn:
            sid = conn.execute(
                "SELECT id FROM roadmap_stages WHERE profile_id=1 ORDER BY sort_order LIMIT 1"
            ).fetchone()["id"]
            original_name = conn.execute(
                "SELECT name FROM roadmap_stages WHERE id=?", (sid,)
            ).fetchone()["name"]
        stage_path = folder / f"stage_{sid}.md"
        assert stage_path.exists(), f"falta {stage_path}"
        with app.get_db() as conn:
            conn.execute(
                "UPDATE roadmap_stages SET name='Otra cosa' WHERE id=?", (sid,)
            )
        app.sync_project_folder(1)
        assert stage_path.exists(), f"{stage_path} debe seguir existiendo tras renombrar"
        assert not (folder / "stage_Otra cosa.md").exists()
        assert not (folder / f"stage_{original_name}.md").exists()
        print("  ✓ stage_<id>.md usa id estable, no el nombre")
    finally:
        app.PROJECTS_DIR = original


def test_new_project_export_uses_stage_files(tmp_path):
    """Un proyecto nuevo exporta stage_<id>.md y no carpetas por variante."""
    _setup_qc_db(tmp_path)
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        c = app.app.test_client()
        r = c.post(
            "/projects/new",
            data={"name": "Nuevo", "topic": "tema", "profile_id": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        with app.get_db() as conn:
            new_id = conn.execute(
                "SELECT id FROM projects WHERE name='Nuevo'"
            ).fetchone()["id"]
        r = c.post(f"/projects/{new_id}/export", follow_redirects=False)
        assert r.status_code == 200
        import io
        import zipfile

        zf = zipfile.ZipFile(io.BytesIO(r.data))
        names = zf.namelist()
        plain_stages = [n for n in names if "/stage_" in n and n.endswith(".md")]
        assert len(plain_stages) == 7, (
            f"esperaba 7 stage_*.md en el ZIP, hay {len(plain_stages)}: {plain_stages}"
        )
        for legacy in ("03_guiones", "04_escenas", "05_metadata", "06_thumbnails"):
            assert not any(legacy in n for n in names), (
                f"carpeta legacy {legacy} no debe existir en el modelo nuevo"
            )
        assert any("00_RESUMEN.md" in n for n in names)
        assert any("08_paquete_completo.json" in n for n in names)
        print(f"  ✓ export de proyecto nuevo usa stage_<id>.md ({len(plain_stages)} archivos)")
    finally:
        app.PROJECTS_DIR = original


def test_legacy_project_export_keeps_legacy_layout(tmp_path):
    """Un proyecto sin project_stages sigue exportando el layout legacy."""
    _setup_qc_db(tmp_path)
    with app.get_db() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status,
                                  created_at, updated_at)
            VALUES (1, 'LegacyP', 'tema', 1, 'ready',
                    '2025-01-01', '2025-01-01')
        """
        )
        conn.execute(
            """
            INSERT INTO research (project_id, content, sources, updated_at)
            VALUES (1, 'investigación', '["s1","s2","s3","s4","s5","s6"]',
                    '2025-01-01')
        """
        )
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        c = app.app.test_client()
        r = c.post("/projects/1/export", follow_redirects=False)
        assert r.status_code == 200
        import io
        import zipfile

        zf = zipfile.ZipFile(io.BytesIO(r.data))
        names = zf.namelist()
        assert any("00_RESUMEN.md" in n for n in names)
        assert any("01_investigacion.md" in n for n in names)
        assert any("08_paquete_completo.json" in n for n in names)
        plain_stages = [n for n in names if "/stage_" in n and n.endswith(".md")]
        assert not plain_stages, (
            f"proyecto legacy no debe usar stage_<id>.md: {plain_stages}"
        )
        print("  ✓ export de proyecto legacy mantiene el layout legacy")
    finally:
        app.PROJECTS_DIR = original


def main():
    import gc
    import tempfile
    from pathlib import Path

    failures: list[tuple[str, BaseException]] = []

    def _safe(label, fn):
        try:
            fn()
        except Exception as e:
            failures.append((label, e))
            print(f"  ✗ {label}: {type(e).__name__}: {e}")
            gc.collect()

    def _with_tmp(label, fn):
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                fn(Path(tmp))
                gc.collect()
        except Exception as e:
            failures.append((label, e))
            print(f"  ✗ {label}: {type(e).__name__}: {e}")

    print("\n=== TESTS DE PARSERS ===")
    _safe("parse_research", test_parse_research)
    _safe("parse_research_with_variations", test_parse_research_with_variations)
    _safe("parse_concept", test_parse_concept)
    _safe("parse_concept_with_body_text", test_parse_concept_with_body_text)
    _safe("parse_script_long", test_parse_script_long)
    _safe("parse_script_short", test_parse_script_short)
    _safe("parse_scenes_json", test_parse_scenes_json)
    _safe("parse_scenes_json_bare", test_parse_scenes_json_bare)
    _safe("parse_prompt_json", test_parse_prompt_json)
    _safe("parse_metadata_youtube_long", test_parse_metadata_youtube_long)
    _safe("parse_metadata_youtube_short", test_parse_metadata_youtube_short)
    _safe(
        "parse_metadata_dispatcher_returns_canonical_shape",
        test_parse_metadata_dispatcher_returns_canonical_shape,
    )
    _safe("parse_metadata_facebook_long", test_parse_metadata_facebook_long)
    _safe("parse_metadata_reels_short", test_parse_metadata_reels_short)
    _safe("parse_thumbnail", test_parse_thumbnail)
    _safe("parse_thumbnail_ignores_other_blocks", test_parse_thumbnail_ignores_other_blocks)

    print("\n=== TESTS DE UTILIDADES ===")
    _safe("count_words", test_count_words)
    _safe("estimate_duration", test_estimate_duration)

    print("\n=== TESTS DE QC ===")
    _with_tmp("missing_research", test_qc_detects_missing_research)
    _with_tmp("short_script", test_qc_detects_short_script)
    _with_tmp("repetition", test_qc_detects_repetition)
    _with_tmp("missing_sources", test_qc_detects_missing_sources)
    _with_tmp("complete_project", test_qc_passes_complete_project)

    print("\n=== TESTS DE EXPORTACIÓN ===")
    _with_tmp("export_creates_zip", test_export_creates_zip)

    print("\n=== TESTS DE SINCRONIZACIÓN DE CARPETA ===")
    _with_tmp("new_project_creates_folder", test_new_project_creates_folder)
    _with_tmp("research_save_syncs_folder", test_research_save_syncs_folder)
    _with_tmp("metadata_save_syncs_folder", test_metadata_save_syncs_folder)
    _with_tmp("export_get_renders_folder", test_export_get_renders_folder)
    _with_tmp("export_resync_action", test_export_resync_action)
    _with_tmp("delete_project_removes_folder", test_delete_project_removes_folder)
    _with_tmp("project_video_lifecycle", test_project_video_lifecycle)

    print("\n=== TESTS DE PROMPTS POR PERFIL ===")
    _with_tmp(
        "resolve_stage_prompt_falls_back_to_config",
        test_resolve_stage_prompt_falls_back_to_config,
    )
    _with_tmp("save_profile_prompt_upsert", test_save_profile_prompt_upsert)
    _with_tmp(
        "resolve_stage_prompt_renders_profile_template",
        test_resolve_stage_prompt_renders_profile_template,
    )
    _with_tmp("resolve_stage_prompt_aliases", test_resolve_stage_prompt_aliases)
    _with_tmp(
        "roadmap_instruction_finds_row_by_roadmap_name",
        test_roadmap_instruction_finds_row_by_roadmap_name,
    )
    _with_tmp(
        "migration_copies_stage_prompts_to_profile_prompts",
        test_migration_copies_stage_prompts_to_profile_prompts,
    )

    print("\n=== TESTS DEL MOTOR DE PLANTILLAS (Fase 1.3) ===")
    _safe("render_substitutes_known_paths", test_render_substitutes_known_paths)
    _safe("render_reports_unknown_paths", test_render_reports_unknown_paths)
    _safe("render_profile_normalizes_platforms_csv", test_render_profile_normalizes_platforms_csv)

    print("\n=== TESTS DE HOUSEKEEPING DE PROMPTS (Fase 1.1) ===")
    _safe(
        "config_has_no_orphan_legacy_keys",
        test_config_has_no_orphan_legacy_keys,
    )

    print("\n=== TESTS DEL REFINER POST-QC (Fase 4) ===")
    _safe("build_refiner_prompt_includes_issues", test_build_refiner_prompt_includes_issues)
    _safe(
        "build_refiner_prompt_respects_original_format",
        test_build_refiner_prompt_respects_original_format,
    )
    _safe("config_visual_style_keywords_is_shared", test_config_visual_style_keywords_is_shared)
    _safe(
        "visual_prompts_reference_shared_keyword_token",
        test_visual_prompts_reference_shared_keyword_token,
    )

    print("\n=== TESTS DE EDICIÓN DE PERFILES ===")
    _with_tmp("profiles_page_renders", test_profiles_page_renders)
    _with_tmp("profiles_update_default", test_profiles_update_default)
    _with_tmp("profiles_update_changes_default", test_profiles_update_changes_default)
    _with_tmp("profiles_update_rejects_empty_name", test_profiles_update_rejects_empty_name)

    print("\n=== TESTS DEL MODELO DE HOJA DE RUTA ===")
    _with_tmp("default_profile_seeds_seven", test_default_profile_seeds_seven_roadmap_stages)
    _with_tmp("new_profile_seeds_seven", test_new_profile_seeds_seven_roadmap_stages)
    _with_tmp("new_project_seeds_seven", test_new_project_seeds_seven_project_stages)
    _with_tmp("project_stage_get_renders", test_project_stage_get_renders)
    _with_tmp("project_stage_post_saves", test_project_stage_post_saves_instruction_and_response)
    _with_tmp("non_empty_response_marks_done", test_non_empty_response_marks_stage_done)
    _with_tmp("update_stage", test_update_stage_renames_reorders_activates_deactivates)
    _with_tmp("delete_stage_cascades", test_delete_stage_cascades_project_stages)
    _with_tmp("migration_backfill", test_migration_backfills_legacy_content_into_project_stages)
    _with_tmp("stage_file_stable_id", test_stage_file_uses_stable_roadmap_id)
    _with_tmp("export_uses_stage_files", test_new_project_export_uses_stage_files)
    _with_tmp("legacy_export_keeps_layout", test_legacy_project_export_keeps_legacy_layout)

    print("\n=== TESTS DE ESTADO POR VIDEO ===")
    _with_tmp("video_stage_status_breakdown", test_video_stage_status_per_video_breakdown)
    _with_tmp("project_stage_status_per_video", test_project_stage_status_aggregates_per_video)
    _with_tmp("qc_state_pending_analyzed_skipped", test_qc_state_pending_analyzed_skipped)
    _with_tmp("pipeline_view_per_video", test_pipeline_view_exposes_per_video_breakdown)

    if failures:
        print(f"\n❌ Fallos restantes ({len(failures)}):")
        for label, err in failures:
            print(f"  - {label}: {type(err).__name__}: {err}")
    else:
        print("\n✅ Todos los tests pasaron\n")


if __name__ == "__main__":
    main()

"""
Tests automatizados para los componentes críticos:
- Parsers (research, concept, script, scenes, prompts, metadata)
- QC engine
- Counters y estimaciones
"""
import sys
import json
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import app


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
    r = app.parse_scenes_json(text_with_json)
    assert r is not None, "no se pudo parsear"
    assert len(r) == 1
    assert r[0]["scene_number"] == 1
    print("  ✓ parse_scenes_json (en bloque markdown)")


def test_parse_scenes_json_bare():
    text = 'Some intro [{"scene_number": 1, "narration_segment": "x", "visual_description": "y", "duration_seconds": 5, "camera_movement": "static", "transition": "cut"}] end'
    r = app.parse_scenes_json(text)
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
    r = app.parse_prompt_json(text)
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
    assert app.estimate_duration_seconds("") == 0
    text = " ".join(["palabra"] * 300)
    assert app.estimate_duration_seconds(text, wpm=150) == 120
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
        i[0] == "research" and i[1] == "error" and "investigación" in i[2].lower()
        for i in issues
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
        body = "objetos " * 50 + "otros términos variados para completar el guion y cumplir mil quinientas palabras"
        conn.execute("""
            INSERT INTO scripts (project_id, type, title, hook, body_full, word_count, updated_at)
            VALUES (1, 'long', 'Test', 'hook', ?, 800, '2025-01-01')
        """, (body,))
    issues = app.run_qc(1)
    has_repetition = any(
        i[0] == "scripts" and "repetida" in i[2].lower()
        for i in issues
    )
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
    has_sources_warning = any(
        i[0] == "research" and "fuentes" in i[2].lower()
        for i in issues
    )
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
        conn.execute("""
            INSERT INTO scripts (project_id, type, title, hook, context, development,
                revelations, conclusion, cta, body_full, word_count, updated_at)
            VALUES (1, 'long', 'Test', 'hook inicial', 'contexto', 'desarrollo',
                'revelaciones finales', 'conclusión reflexiva', 'suscríbete',
                ?, 750, '2025-01-01')
        """, (body,))
        # 6 escenas
        for i in range(6):
            conn.execute("""
                INSERT INTO scenes (project_id, scene_number, narration, visual_description,
                    duration_seconds, camera_movement, transition, updated_at)
                VALUES (1, ?, 'narración escena', 'visual escena', 30, 'zoom', 'fade', '2025-01-01')
            """, (i + 1,))
        # Metadata
        conn.execute("""
            INSERT INTO metadata_records (project_id, platform, titles, updated_at)
            VALUES (1, 'youtube', '[]', '2025-01-01')
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
            conn.execute("""
                INSERT INTO scenes (project_id, scene_number, narration, visual_description,
                    duration_seconds, updated_at)
                VALUES (1, ?, 'narración', 'visual', 30, '2025-01-01')
            """, (i + 1,))
        conn.execute("""
            INSERT INTO metadata_records (project_id, platform, titles, description, updated_at)
            VALUES (1, 'youtube', '["t1"]', 'desc', '2025-01-01')
        """)
    # Override projects dir
    import os
    test_projects = tmp_path / "projects"
    test_projects.mkdir()
    original = app.PROJECTS_DIR
    app.PROJECTS_DIR = test_projects
    try:
        from app import export
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
            assert any("07_paquete_completo.json" in n for n in names)
        print(f"  ✓ export crea ZIP con {len(names)} archivos")
    finally:
        app.PROJECTS_DIR = original


# ==========================================================================
# Runner
# ==========================================================================

def main():
    import tempfile
    import gc
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

    print("\n✅ Todos los tests pasaron\n")


if __name__ == "__main__":
    main()

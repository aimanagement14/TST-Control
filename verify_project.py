"""
Verificación end-to-end del pipeline genérico de siete etapas.

Ejecuta el flujo completo contra ``app.test_client()`` con datos
simulados del LLM (modo manual exclusivo, >= 2.0):

- Crea (o reinicia) un proyecto sintético con ``id=PROJECT_ID``.
- Asegura sus ``project_stages``: research → concept → scripts →
  scenes → metadata → thumbnails → qc.
- Para cada etapa, ``POST /projects/<id>/stages/<stage_id>`` con
  ``action=save`` y una instrucción + respuesta Markdown
  representativas.
- ``action=generate`` sobre la primera etapa: devuelve el bloque
  manual exclusivo y **no** persiste la respuesta en BD.
- Comprueba el dashboard y la vista del proyecto.
- Verifica ``7/7`` etapas completas vía ``project_stage_status``.
- Comprueba los archivos en disco: ``00_RESUMEN.md`` +
  ``stage_<roadmap_stage_id>.md`` por etapa + ``08_paquete_completo.json``.
- Comprueba que renombrar el proyecto renombra la carpeta pero **no**
  los ``stage_<roadmap_stage_id>.md`` (el ID en el nombre se mantiene).
- Comprueba que desactivar (``is_active=0``) una etapa no genera
  su ``.md`` y la hace invisible para ``project_stage_status``.
- ``POST /projects/<id>/export action=zip`` devuelve el ZIP con los
  mismos archivos.

PROJECT_ID se eligió alto (2) para no chocar con proyectos reales del
usuario. Renombrar este archivo o cambiar el id es trivial.
"""

import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
import app

PROJECT_ID = 2

PROJECT_NAME = "Verificacion pipeline"
PROJECT_TOPIC = "Tema sintetico para smoke test del pipeline de 7 etapas"

VERIFY_PROFILE_NAME = "__verify_project__"

STAGE_FIXTURES = {
    "research": (
        "Investiga el tema con hechos verificables y fuentes.",
        "# Investigación\n"
        "## Resumen\n"
        "Texto de la investigación sintética del flujo genérico de siete etapas.\n"
        "## Hechos confirmados\n"
        "- Hecho verificable A con su fuente.\n"
        "- Hecho verificable B con su fuente.\n"
        "- Hecho verificable C con su fuente.\n"
        "## Fuentes\n"
        "- https://example.org/fuente-1\n"
        "- https://example.org/fuente-2\n"
        "- https://example.org/fuente-3\n",
    ),
    "concept": (
        "Define ángulo, tesis y ganchos del documental.",
        "# Concepto\n"
        "## Ángulo\n"
        "Separar la realidad verificable del ruido viral.\n"
        "## Tesis\n"
        "La realidad geológica es más asombrosa que el mito.\n"
        "## Puntos clave\n"
        "1. Punto uno del concepto.\n"
        "2. Punto dos del concepto.\n",
    ),
    "scripts": (
        "Escribe el guion completo del documental.",
        "# Guiones\n"
        "Representación genérica del contenido de guiones para el pipeline "
        "de siete etapas. Incluye el cuerpo necesario para verificar la "
        "persistencia del bloque Markdown en la nueva ``project_stage``.\n",
    ),
    "scenes": (
        "Convierte el guion en una lista de escenas visuales.",
        "# Escenas\n"
        "## ESCENA 1\n"
        "TEXTO AUDIO: Frase de prueba de la primera escena.\n"
        "IMAGEN: Imagen representativa de la escena uno.\n"
        "_Cámara: estático · Transición: corte seco · Duración: 15s_\n"
        "## ESCENA 2\n"
        "TEXTO AUDIO: Frase de la segunda escena.\n"
        "IMAGEN: Imagen representativa de la escena dos.\n"
        "_Cámara: travelling · Transición: fundido · Duración: 20s_\n",
    ),
    "metadata": (
        "Genera metadata publicable (títulos, descripción, tags).",
        "# Metadata\n"
        "Representación genérica del contenido de metadata para el pipeline "
        "de siete etapas. Cubre títulos, descripción, capítulos y tags.\n",
    ),
    "thumbnails": (
        "Genera prompts visuales para las miniaturas.",
        "# Miniaturas\n"
        "Representación genérica del contenido de miniaturas para el "
        "pipeline de siete etapas, con prompts visuales cinematográficos.\n",
    ),
    "qc": (
        "Revisa el paquete y emite el informe de calidad.",
        "# Control de calidad\n"
        "- [info] Revisión representativa del paquete del pipeline "
        "genérico de siete etapas.\n",
    ),
}

EXPECTED_ORDER = (
    "research",
    "concept",
    "scripts",
    "scenes",
    "metadata",
    "thumbnails",
    "qc",
)


def reset_project():
    """Borra el proyecto sintético (si existe) y lo recrea con un perfil sintético dedicado.

    Garantiza que existe un perfil ``__verify_project__`` con las siete
    etapas activas en el orden de ``EXPECTED_ORDER`` y, si ya existía,
    reemplaza sus ``roadmap_stages`` y los ``project_stages`` de los
    proyectos asociados. No toca perfiles ni proyectos reales del
    usuario.
    """
    with app.get_db() as conn:
        row = conn.execute(
            "SELECT name FROM projects WHERE id=?", (PROJECT_ID,)
        ).fetchone()
        if row:
            app.delete_project_folder(PROJECT_ID, row["name"])
            conn.execute("DELETE FROM projects WHERE id=?", (PROJECT_ID,))

    for orphan in app.PROJECTS_DIR.glob(f"*_{PROJECT_ID}"):
        if orphan.is_dir():
            shutil.rmtree(orphan)
        elif orphan.suffix == ".zip":
            orphan.unlink()

    now = app.now_iso()
    with app.get_db() as conn:
        profile = conn.execute(
            "SELECT id FROM profiles WHERE name=?", (VERIFY_PROFILE_NAME,)
        ).fetchone()
        if profile:
            profile_id = profile["id"]
            conn.execute(
                "DELETE FROM project_stages WHERE project_id IN "
                "(SELECT id FROM projects WHERE profile_id=?)",
                (profile_id,),
            )
            conn.execute(
                "DELETE FROM roadmap_stages WHERE profile_id=?",
                (profile_id,),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO profiles (name, is_default, created_at)
                VALUES (?, 0, ?)
                """,
                (VERIFY_PROFILE_NAME, now),
            )
            profile_id = cur.lastrowid
        for idx, name in enumerate(EXPECTED_ORDER):
            conn.execute(
                """
                INSERT INTO roadmap_stages
                    (profile_id, name, instruction, sort_order, is_active,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    profile_id,
                    name,
                    STAGE_FIXTURES[name][0],
                    idx,
                    now,
                    now,
                ),
            )
        conn.execute(
            """
            INSERT INTO projects
                (id, name, topic, profile_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'research', ?, ?)
            """,
            (
                PROJECT_ID,
                PROJECT_NAME,
                PROJECT_TOPIC,
                profile_id,
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )
    app.sync_project_stages_for_project(PROJECT_ID)


def log(stage, msg, ok=True):
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark} {stage}: {msg}")


def main():
    client = app.app.test_client()
    failures: list[str] = []

    def check(label, ok, detail=""):
        ok = bool(ok)
        log(label, detail if detail else ("sí" if ok else "NO"), ok)
        if not ok:
            failures.append(label)

    print("=== 0) Bootstrap ===")
    reset_project()
    with app.get_db() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM projects WHERE id=?", (PROJECT_ID,)
        ).fetchone()["n"]
    check("Proyecto sintético recreado", n == 1, f"id={PROJECT_ID}")

    stages = app.load_project_stages(PROJECT_ID)
    check("Hay 7 project_stages", len(stages) == 7, f"{len(stages)} filas")
    ordered_names = [s["stage_name"] for s in stages]
    check(
        "Orden = research → ... → qc",
        ordered_names == list(EXPECTED_ORDER),
        f"{ordered_names}",
    )
    ps_id_by_name = {s["stage_name"]: s["id"] for s in stages}
    rs_id_by_name = {s["stage_name"]: s["roadmap_stage_id"] for s in stages}

    print("\n=== 1) Dashboard y vista de proyecto ===")
    r = client.get("/")
    check("GET / status 200", r.status_code == 200, f"status {r.status_code}")
    check("GET / contiene marca", b"Todo Sobre Todo" in r.data)

    r = client.get(f"/projects/{PROJECT_ID}")
    check("GET /projects/<id> status 200", r.status_code == 200, f"status {r.status_code}")
    check(
        "GET /projects/<id> contiene el nombre",
        PROJECT_NAME.encode("utf-8") in r.data,
    )
    check("GET /projects/<id> muestra la hoja de ruta", b"Hoja de ruta" in r.data)

    print("\n=== 2) action=save por etapa (ruta genérica) ===")
    for name in EXPECTED_ORDER:
        instruction, response = STAGE_FIXTURES[name]
        r = client.post(
            f"/projects/{PROJECT_ID}/stages/{ps_id_by_name[name]}",
            data={
                "action": "save",
                "instruction": instruction,
                "response": response,
            },
            follow_redirects=False,
        )
        check(f"{name} save", r.status_code in (200, 302), f"status {r.status_code}")

    with app.get_db() as conn:
        rows = {
            row["stage_name"]: dict(row)
            for row in conn.execute(
                """
                SELECT rs.name AS stage_name, ps.instruction, ps.response
                FROM project_stages ps
                JOIN roadmap_stages rs ON rs.id = ps.roadmap_stage_id
                WHERE ps.project_id=?
                """,
                (PROJECT_ID,),
            ).fetchall()
        }
    for name, (instruction, response) in STAGE_FIXTURES.items():
        row = rows.get(name, {})
        saved_resp = (row.get("response") or "").strip()
        saved_inst = (row.get("instruction") or "").strip()
        check(
            f"{name} response persistida",
            saved_resp == response.strip(),
            f"{len(saved_resp)} chars",
        )
        check(
            f"{name} instruction persistida",
            saved_inst == instruction.strip(),
            f"{len(saved_inst)} chars",
        )

    print("\n=== 3) action=generate (modo manual, sin guardar) ===")
    research_id = ps_id_by_name["research"]
    with app.get_db() as conn:
        before = (
            conn.execute(
                "SELECT response FROM project_stages WHERE id=?", (research_id,)
            ).fetchone()["response"]
            or ""
        )
    r = client.post(
        f"/projects/{PROJECT_ID}/stages/{research_id}",
        data={
            "action": "generate",
            "instruction": "instruccion generada de prueba",
        },
        follow_redirects=False,
    )
    check("generate status 200", r.status_code == 200, f"status {r.status_code}")
    body = r.data.decode("utf-8", errors="replace")
    check(
        "generate devuelve el bloque manual exclusivo",
        "## [MODO MANUAL" in body,
        "marker presente",
    )
    with app.get_db() as conn:
        after = (
            conn.execute(
                "SELECT response FROM project_stages WHERE id=?", (research_id,)
            ).fetchone()["response"]
            or ""
        )
    check(
        "generate NO persiste la respuesta",
        after == before,
        f"{len(before)}ch -> {len(after)}ch",
    )

    print("\n=== 4) 7/7 completas + carpeta sincronizada (modelo nuevo) ===")
    with app.get_db() as conn:
        proj = dict(
            conn.execute(
                "SELECT * FROM projects WHERE id=?", (PROJECT_ID,)
            ).fetchone()
        )
    status = app.project_stage_status(proj)
    done = sum(1 for v in status.values() if v)
    check("7/7 etapas marcadas como hechas", done == 7, f"{done}/7")
    check(
        "Claves del status = conjunto esperado",
        set(status.keys()) == set(EXPECTED_ORDER),
        f"{sorted(status.keys())}",
    )

    folder, written = app.sync_project_folder(PROJECT_ID)
    expected_files = (
        {"00_RESUMEN.md", "08_paquete_completo.json"}
        | {f"stage_{rs_id_by_name[n]}.md" for n in EXPECTED_ORDER}
    )
    check(
        "Carpeta contiene exactamente 9 archivos esperados",
        set(written) == expected_files,
        f"faltan={sorted(expected_files - set(written))} "
        f"sobran={sorted(set(written) - expected_files)}",
    )
    resumen = (folder / "00_RESUMEN.md").read_text(encoding="utf-8")
    check("00_RESUMEN contiene el tema", PROJECT_TOPIC in resumen)
    check("00_RESUMEN contiene el nombre", PROJECT_NAME in resumen)

    bundle = json.loads((folder / "08_paquete_completo.json").read_text(encoding="utf-8"))
    check(
        "bundle tiene 7 project_stages",
        len(bundle.get("project_stages", [])) == 7,
        f"{len(bundle.get('project_stages', []))}",
    )
    check(
        "bundle tiene 7 roadmap_stages activos",
        len(bundle.get("roadmap_stages", [])) == 7,
        f"{len(bundle.get('roadmap_stages', []))}",
    )

    print("\n=== 5) Renombrar no cambia los filenames internos ===")
    NEW_NAME = "Otro Nombre Con Acentos"
    with app.get_db() as conn:
        conn.execute(
            "UPDATE projects SET name=?, updated_at=? WHERE id=?",
            (NEW_NAME, "2026-02-01T00:00:00", PROJECT_ID),
        )
    renamed_folder, renamed_written = app.sync_project_folder(PROJECT_ID)
    expected_renamed = app.safe_project_dir(PROJECT_ID, NEW_NAME).name
    check(
        "La carpeta tiene el nuevo nombre",
        renamed_folder.name == expected_renamed,
        f"{renamed_folder.name}",
    )
    check(
        "Filenames NO cambian tras renombrar",
        set(renamed_written) == expected_files,
        f"diffs {sorted(set(renamed_written) ^ expected_files)}",
    )
    check(
        "Cada stage_<rsid>.md sigue presente",
        all(
            (renamed_folder / f"stage_{rs_id_by_name[n]}.md").exists()
            for n in EXPECTED_ORDER
        ),
        "todos",
    )
    with app.get_db() as conn:
        conn.execute(
            "UPDATE projects SET name=?, updated_at=? WHERE id=?",
            (PROJECT_NAME, "2026-01-01T00:00:00", PROJECT_ID),
        )

    print("\n=== 6) Etapa desactivada: sin MD, sin acceso visible ===")
    DISABLED = "qc"
    disabled_rs = rs_id_by_name[DISABLED]
    with app.get_db() as conn:
        conn.execute(
            "UPDATE roadmap_stages SET is_active=0, updated_at=? WHERE id=?",
            ("2026-03-01T00:00:00", disabled_rs),
        )
        proj2 = dict(
            conn.execute(
                "SELECT * FROM projects WHERE id=?", (PROJECT_ID,)
            ).fetchone()
        )
    disabled_folder, disabled_written = app.sync_project_folder(PROJECT_ID)
    disabled_file = disabled_folder / f"stage_{disabled_rs}.md"
    check(
        f"Etapa '{DISABLED}' desactivada NO genera MD",
        not disabled_file.exists(),
        f"{disabled_file.name}",
    )
    check(
        "El set de archivos cae a 8 (-1 desactivada)",
        len(disabled_written) == len(expected_files) - 1,
        f"{len(disabled_written)} archivos",
    )
    check(
        "El MD de la desactivada tampoco está en la lista escrita",
        f"stage_{disabled_rs}.md" not in disabled_written,
    )

    status_disabled = app.project_stage_status(proj2)
    check(
        "project_stage_status omite la etapa desactivada",
        DISABLED not in status_disabled,
        f"{sorted(status_disabled.keys())}",
    )
    check(
        "Conteo activo = 6 (no 7)",
        sum(1 for v in status_disabled.values() if v) == 6,
        f"{sum(1 for v in status_disabled.values() if v)}/6",
    )

    with app.get_db() as conn:
        conn.execute(
            "UPDATE roadmap_stages SET is_active=1, updated_at=? WHERE id=?",
            ("2026-04-01T00:00:00", disabled_rs),
        )
    app.sync_project_folder(PROJECT_ID)

    print("\n=== 7) Export ZIP ===")
    r = client.post(
        f"/projects/{PROJECT_ID}/export",
        data={"action": "zip"},
        follow_redirects=False,
    )
    check("Export status 200", r.status_code == 200, f"status {r.status_code}")
    check(
        "Export devuelve un ZIP (PK magic)",
        r.data[:2] == b"PK",
        f"primeros bytes={r.data[:4]!r}",
    )
    zf = zipfile.ZipFile(io.BytesIO(r.data))
    names = zf.namelist()
    for token in ("00_RESUMEN.md", "08_paquete_completo.json"):
        check(f"ZIP contiene {token}", any(token in n for n in names), token)
    for name in EXPECTED_ORDER:
        token = f"stage_{rs_id_by_name[name]}.md"
        check(f"ZIP contiene {token}", any(token in n for n in names), token)

    resumen_zip = next(
        zf.read(n).decode("utf-8")
        for n in names
        if n.endswith("00_RESUMEN.md")
    )
    check("ZIP resumen contiene el tema", PROJECT_TOPIC in resumen_zip)
    bundle_zip = json.loads(
        next(
            zf.read(n).decode("utf-8")
            for n in names
            if n.endswith("08_paquete_completo.json")
        )
    )
    check(
        "ZIP bundle tiene 7 project_stages",
        len(bundle_zip.get("project_stages", [])) == 7,
        f"{len(bundle_zip.get('project_stages', []))}",
    )

    print("\n" + "=" * 60)
    if failures:
        print(f"  {len(failures)} comprobaciones fallaron:")
        for name in failures:
            print(f"    - {name}")
        print("=" * 60)
        sys.exit(1)
    print("  Todas las comprobaciones pasaron en verde")
    print(f"  ZIP: {len(names)} archivos, {len(r.data)} bytes")
    print("=" * 60)


if __name__ == "__main__":
    main()

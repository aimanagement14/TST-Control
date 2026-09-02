"""Reglas QC (quality control) del pipeline.

Funciones:
- `run_qc(project_id)`: ejecuta todos los checks y devuelve la lista
  de issues como tuplas `(stage, severity, message, field)`.
- `save_qc_issues(project_id, issues)`: persiste los issues en
  `qc_issues` (DELETE + INSERT).

Ambas usan `get_db()`, `CONFIG["qc"]["checks"]`, `format_timecode` y
`now_iso()` desde app.py. Se accede a esos simbolos via local import
para evitar ciclos.
"""

from __future__ import annotations

import json
import re
from collections import Counter


def run_qc(project_id: int) -> list[tuple[str, str, str, str]]:
    """Ejecuta todos los checks y devuelve la lista de issues."""
    # Import local para evitar ciclo.
    from app import CONFIG, format_timecode, get_db

    issues: list[tuple[str, str, str, str]] = []
    with get_db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            return issues
        project = dict(project)
        research = conn.execute("SELECT * FROM research WHERE project_id=?", (project_id,)).fetchone()
        concept = conn.execute("SELECT * FROM concept WHERE project_id=?", (project_id,)).fetchone()
        scripts = [dict(r) for r in conn.execute("SELECT * FROM scripts WHERE project_id=?", (project_id,)).fetchall()]
        scenes = [dict(r) for r in conn.execute("SELECT * FROM scenes WHERE project_id=? ORDER BY scene_number", (project_id,)).fetchall()]
        prompts = [dict(r) for r in conn.execute("SELECT * FROM prompts WHERE project_id=?", (project_id,)).fetchall()]
        metadata = [dict(r) for r in conn.execute("SELECT * FROM metadata_records WHERE project_id=?", (project_id,)).fetchall()]

    scenes_by_script: dict[int, list[dict]] = {}
    for sc in scenes:
        scenes_by_script.setdefault(sc["script_id"], []).append(sc)

    cfg = CONFIG["qc"]["checks"]

    # Investigación
    if not research or not research["content"]:
        issues.append(("research", "error", "Falta la investigación", "content"))
    else:
        sources = json.loads(research["sources"] or "[]")
        if len(sources) < cfg["min_sources"]:
            issues.append((
                "research", "warning",
                f"Solo {len(sources)} fuentes (mínimo recomendado: {cfg['min_sources']})",
                "sources",
            ))

    # Concepto
    if not concept or not concept["angle"]:
        issues.append(("concept", "error", "Falta el concepto", "angle"))

    # Guiones
    long_s = next((s for s in scripts if s["type"] == "long"), None)
    short_s = next((s for s in scripts if s["type"] == "short"), None)

    for s, ttype, target, min_w, max_w in [
        (long_s, "long", cfg["target_duration_long_seconds"], cfg["min_words_long"], cfg["max_words_long"]),
        (short_s, "short", cfg["target_duration_short_seconds"], cfg["min_words_short"], cfg["max_words_short"]),
    ]:
        if not s:
            issues.append(("scripts", "info", f"Falta el guion {ttype}", ttype))
            continue
        wc = s["word_count"]
        tlabel = f"{ttype} (5 min)" if ttype == "long" else f"{ttype} (1 min)"
        if wc < min_w:
            issues.append(("scripts", "warning",
                f"Guion {tlabel} tiene {wc} palabras (mínimo {min_w})", ttype))
        elif wc > max_w:
            issues.append(("scripts", "warning",
                f"Guion {tlabel} tiene {wc} palabras (máximo {max_w})", ttype))
        # Duración estimada
        if wc > 0:
            wpm = project.get("narration_speed") or 150
            est = int(wc / wpm * 60)
            target = cfg[f"target_duration_{ttype}_seconds"]
            if abs(est - target) > 30:
                issues.append(("scripts", "info",
                    f"Duración estimada del guion {tlabel}: {format_timecode(est)} "
                    f"(objetivo {format_timecode(target)})", ttype))
        # Hook presente
        if not s["hook"]:
            issues.append(("scripts", "error", f"Guion {tlabel} sin hook definido", "hook"))
        # Repeticiones
        full = s["body_full"] or ""
        words = re.findall(r"\b\w{6,}\b", full.lower())
        c = Counter(words)
        for word, n in c.most_common(10):
            if n >= cfg["repetition_threshold"]:
                issues.append(("scripts", "warning",
                    f"Palabra repetida {n}× en el guion {tlabel}: «{word}»", ttype))
                break
        # CTA
        if not s["cta"]:
            issues.append(("scripts", "warning", f"Guion {tlabel} sin CTA", "cta"))

    # Escenas
    if scripts and not scenes:
        issues.append(("scenes", "error", "No hay escenas", "scenes"))
    for s in scripts:
        scs = scenes_by_script.get(s["id"], [])
        min_n = cfg[f"min_scenes_{'long' if s['type'] == 'long' else 'short'}"]
        label = "guion 5 min" if s["type"] == "long" else "guion 1 min"
        if not scs:
            issues.append(("scenes", "warning",
                f"Faltan escenas para el {label}", s["type"]))
        elif len(scs) < min_n:
            issues.append(("scenes", "warning",
                f"Solo {len(scs)} escenas en el {label} (mínimo recomendado: {min_n})",
                s["type"]))

    # Metadata
    if scripts and not metadata:
        issues.append(("metadata", "info", "No se ha generado metadata", "metadata"))

    # Coherencia investigación / guiones
    if research:
        unv = json.loads(research["unverified"] or "[]")
        if unv and (long_s or short_s):
            issues.append(("research", "warning",
                f"Hay {len(unv)} afirmaciones que requieren verificación en la investigación", "unverified"))

    return issues


def save_qc_issues(project_id: int, issues: list[tuple[str, str, str, str]]) -> None:
    """Persiste los issues en `qc_issues` (DELETE + INSERT por issue)."""
    from app import get_db, now_iso

    with get_db() as conn:
        conn.execute("DELETE FROM qc_issues WHERE project_id=?", (project_id,))
        for stage, severity, message, field in issues:
            conn.execute("""
                INSERT INTO qc_issues (project_id, stage, severity, message, field, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (project_id, stage, severity, message, field, now_iso()))

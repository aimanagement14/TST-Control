"""Reglas QC (quality control) del pipeline.

La comprobación recorre todos los videos del proyecto; los dos videos base
se conservan como referencias compatibles y los videos añadidos heredan
el mismo flujo de guion, escenas, metadata y miniatura.

Cada issue lleva el ``video_id`` al que afecta (o ``None`` para issues
de proyecto). La UI del stepper lo usa para reflejar el estado de QC
por video.
"""

from __future__ import annotations

import json
import re
from collections import Counter


def run_qc(project_id: int) -> list[tuple[str, str, str, str, int | None]]:
    """Ejecuta todos los checks y devuelve la lista de issues.

    Cada issue es ``(stage, severity, message, field, video_id)``. Los
    issues de proyecto (sin video concreto) llevan ``video_id=None``.
    """
    from app import CONFIG, format_timecode, get_db
    issues: list[tuple[str, str, str, str, int | None]] = []
    with get_db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            return issues
        project = dict(project)
        research = conn.execute(
            "SELECT * FROM research WHERE project_id=?", (project_id,)
        ).fetchone()
        concept = conn.execute(
            "SELECT * FROM concept WHERE project_id=?", (project_id,)
        ).fetchone()
        videos = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM videos WHERE project_id=? ORDER BY sort_order, id",
                (project_id,),
            ).fetchall()
        ]
        if not videos:
            script_types = {
                row["type"]
                for row in conn.execute(
                    "SELECT DISTINCT type FROM scripts WHERE project_id=? AND type IN ('long', 'short')",
                    (project_id,),
                ).fetchall()
            }
            legacy_names = {"long": "Video 5 min", "short": "Video 1 min"}
            videos = [
                {
                    "id": None,
                    "project_id": project_id,
                    "key": script_type,
                    "name": legacy_names[script_type],
                    "script_type": script_type,
                    "format": "16:9 horizontal" if script_type == "long" else "9:16 vertical",
                    "sort_order": index,
                }
                for index, script_type in enumerate(("long", "short"))
                if script_type in script_types
            ]
        scripts = [
            dict(row)
            for row in conn.execute(
                """
                SELECT s.*, v.name AS video_name, v.key AS video_key,
                       v.script_type AS video_script_type
                FROM scripts s
                LEFT JOIN videos v ON v.id=s.video_id
                WHERE s.project_id=?
                """,
                (project_id,),
            ).fetchall()
        ]
        scenes = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM scenes WHERE project_id=? ORDER BY scene_number", (project_id,)
            ).fetchall()
        ]
        metadata = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM metadata_records WHERE project_id=?", (project_id,)
            ).fetchall()
        ]
        profile = conn.execute(
            "SELECT narration_speed FROM profiles WHERE id=?", (project["profile_id"],)
        ).fetchone()

    scenes_by_script: dict[int, list[dict]] = {}
    for scene in scenes:
        scenes_by_script.setdefault(scene["script_id"], []).append(scene)

    cfg = CONFIG["qc"]["checks"]
    narration_speed = profile["narration_speed"] if profile and profile["narration_speed"] else 150

    if not research or not research["content"]:
        issues.append(("research", "error", "Falta la investigación", "content", None))
    else:
        sources = json.loads(research["sources"] or "[]")
        if len(sources) < cfg["min_sources"]:
            issues.append(
                (
                    "research",
                    "warning",
                    f"Solo {len(sources)} fuentes (mínimo recomendado: {cfg['min_sources']})",
                    "sources",
                    None,
                )
            )

    if not concept or not concept["angle"]:
        issues.append(("concept", "error", "Falta el concepto", "angle", None))

    scripts_by_video: dict[int | None, dict] = {}
    for script in scripts:
        scripts_by_video.setdefault(script.get("video_id"), script)
    for video in videos:
        video_id = video.get("id")
        selected_script: dict | None = scripts_by_video.get(video_id)
        prompt_type = video["script_type"]
        if not selected_script:
            label = video["name"] or video["key"]
            issues.append(("scripts", "info", f"Falta el guion de {label}", video["key"], video_id))
            continue
        label = "guion long (5 min)" if video["key"] == "long" else "guion short (1 min)" if video["key"] == "short" else video["name"]
        min_words = cfg[f"min_words_{prompt_type}"]
        max_words = cfg[f"max_words_{prompt_type}"]
        target = cfg[f"target_duration_{prompt_type}_seconds"]
        word_count = selected_script["word_count"] or 0
        if word_count < min_words:
            issues.append(
                (
                    "scripts",
                    "warning",
                    f"Guion {label} tiene {word_count} palabras (mínimo {min_words})",
                    video["key"],
                    video_id,
                )
            )
        elif word_count > max_words:
            issues.append(
                (
                    "scripts",
                    "warning",
                    f"Guion {label} tiene {word_count} palabras (máximo {max_words})",
                    video["key"],
                    video_id,
                )
            )
        estimated = int(word_count / narration_speed * 60) if word_count else 0
        if word_count and abs(estimated - target) > 30:
            issues.append(
                (
                    "scripts",
                    "info",
                    f"Duración estimada del guion {label}: {format_timecode(estimated)} "
                    f"(objetivo {format_timecode(target)})",
                    video["key"],
                    video_id,
                )
            )
        if not selected_script["hook"]:
            issues.append(("scripts", "error", f"Guion {label} sin hook definido", "hook", video_id))
        full = selected_script["body_full"] or ""
        words = re.findall(r"\b\w{6,}\b", full.lower())
        counts = Counter(words)
        for word, number in counts.most_common(10):
            if number >= cfg["repetition_threshold"]:
                issues.append(
                    (
                        "scripts",
                        "warning",
                        f"Palabra repetida {number}× en el guion {label}: «{word}»",
                        video["key"],
                        video_id,
                    )
                )
                break
        if not selected_script["cta"]:
            issues.append(("scripts", "warning", f"Guion {label} sin CTA", "cta", video_id))

        script_scenes = scenes_by_script.get(selected_script["id"], [])
        min_scenes = cfg[f"min_scenes_{prompt_type}"]
        if not script_scenes:
            issues.append(("scenes", "warning", f"Faltan escenas para {label}", video["key"], video_id))
        elif len(script_scenes) < min_scenes:
            issues.append(
                (
                    "scenes",
                    "warning",
                    f"Solo {len(script_scenes)} escenas en {label} (mínimo recomendado: {min_scenes})",
                    video["key"],
                    video_id,
                )
            )

    if scripts and not scenes:
        issues.append(("scenes", "error", "No hay escenas", "scenes", None))
    if scripts and not metadata:
        issues.append(("metadata", "info", "No se ha generado metadata", "metadata", None))

    if research:
        unverified = json.loads(research["unverified"] or "[]")
        if unverified and scripts:
            issues.append(
                (
                    "research",
                    "warning",
                    f"Hay {len(unverified)} afirmaciones que requieren verificación en la investigación",
                    "unverified",
                    None,
                )
            )

    return issues


def save_qc_issues(project_id: int, issues: list[tuple[str, str, str, str, int | None]]) -> None:
    """Persiste los issues en `qc_issues` (DELETE + INSERT por issue)."""
    from app import get_db, now_iso

    with get_db() as conn:
        conn.execute("DELETE FROM qc_issues WHERE project_id=?", (project_id,))
        for stage, severity, message, field, video_id in issues:
            conn.execute(
                """
                INSERT INTO qc_issues (project_id, stage, severity, message, field, video_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (project_id, stage, severity, message, field, video_id, now_iso()),
            )

"""Estado por video de cada etapa del pipeline.

Investigar y Concepto son etapas de proyecto: viven una sola vez en
``project_stages``. Guiones, Escenas, Metadata, Miniaturas y QC son
etapas por video: cada rama de ``videos`` aporta su propio guion,
escenas, metadata, miniatura y resultado de QC.

Contrato de pureza:

- PURAS (no necesitan Flask): ``video_stage_status``, ``stage_breakdown_for``.
- REQUIEREN contexto Flask: ``_stage_url`` (``url_for``),
  ``build_video_urls`` y ``attach_breakdown_urls`` (``has_app_context``
  la convierte en no-op fuera de una app).
"""

from __future__ import annotations

from typing import Any

PER_VIDEO_STAGES = frozenset({"scripts", "scenes", "metadata", "thumbnails", "qc"})


def _stage_url(project_id: int, stage_key: str, video_id: int | None) -> str:
    """URL de la etapa per-video. Sólo se invoca bajo contexto Flask."""
    from flask import url_for
    if stage_key == "scripts":
        return url_for("scripts", project_id=project_id, video_id=video_id)
    if stage_key == "scenes":
        return url_for("scenes", project_id=project_id, video_id=video_id)
    if stage_key == "metadata":
        return url_for("metadata", project_id=project_id, video_id=video_id)
    if stage_key == "thumbnails":
        return url_for("thumbnails", project_id=project_id, video_id=video_id)
    if stage_key == "qc":
        return url_for("qc", project_id=project_id)
    return url_for("view_project", project_id=project_id)


def build_video_urls(project_id: int, video_id: int | None) -> dict[str, str]:
    """Adjunta las URLs de las etapas per-video para un video concreto.

    Se ejecuta dentro del contexto de Flask (el caller garantiza request
    context). Lo separamos de ``video_stage_status`` para que esa
    función sea pura y testeable sin app context.
    """
    return {
        "scripts": _stage_url(project_id, "scripts", video_id),
        "scenes": _stage_url(project_id, "scenes", video_id),
        "metadata": _stage_url(project_id, "metadata", video_id),
        "thumbnails": _stage_url(project_id, "thumbnails", video_id),
        "qc": _stage_url(project_id, "qc", video_id),
    }


def _load_videos(project_id: int) -> list[dict]:
    """Lee los videos del proyecto. Si la tabla ``videos`` está vacía,
    devuelve filas virtuales para los videos base que aún no se
    sembraron (compatibilidad con proyectos sintéticos).
    """
    from app import get_db
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE project_id=? ORDER BY sort_order, id",
            (project_id,),
        ).fetchall()
    if rows:
        return [dict(r) for r in rows]
    return [
        {"id": None, "project_id": project_id, "key": "long",
         "name": "Video 5 min", "script_type": "long",
         "format": "16:9 horizontal", "sort_order": 0},
        {"id": None, "project_id": project_id, "key": "short",
         "name": "Video 1 min", "script_type": "short",
         "format": "9:16 vertical", "sort_order": 1},
    ]


def video_stage_status(project_id: int) -> list[dict[str, Any]]:
    """Estado por video y por etapa para un proyecto.

    Devuelve una lista ordenada de videos, cada uno con::

        {
            "id": int | None,
            "key": str,
            "name": str,
            "script_type": str,
            "stages": {
                "scripts": bool,
                "scenes": bool,
                "metadata": bool,
                "thumbnails": bool,
                "qc": bool,
            },
        }

    Lista vacía si el proyecto no tiene videos y no hay datos legacy.
    No toca ``url_for`` para poder ejecutarse sin contexto de Flask
    (CLI, tests). Las URLs se adjuntan aparte con ``build_video_urls``.
    """
    videos = _load_videos(project_id)
    if not videos:
        return []

    from app import get_db
    with get_db() as conn:
        script_rows = [
            dict(r) for r in conn.execute(
                """
                SELECT s.*, v.key AS v_key
                FROM scripts s
                LEFT JOIN videos v ON v.id = s.video_id
                WHERE s.project_id=?
                """,
                (project_id,),
            ).fetchall()
        ]
        scene_counts: dict[int, int] = {}
        for r in conn.execute(
            "SELECT script_id, COUNT(*) AS n FROM scenes "
            "WHERE project_id=? GROUP BY script_id",
            (project_id,),
        ).fetchall():
            scene_counts[r["script_id"]] = r["n"]
        metadata_keys = {
            r["v_key"]
            for r in conn.execute(
                """
                SELECT DISTINCT v.key AS v_key
                FROM metadata_records m
                LEFT JOIN videos v ON v.id = m.video_id
                WHERE m.project_id=?
                """,
                (project_id,),
            ).fetchall()
            if r["v_key"]
        }
        thumbnail_keys = {
            r["v_key"]
            for r in conn.execute(
                """
                SELECT DISTINCT v.key AS v_key
                FROM thumbnail_records t
                LEFT JOIN videos v ON v.id = t.video_id
                WHERE t.project_id=?
                  AND t.prompt IS NOT NULL AND TRIM(t.prompt) != ''
                """,
                (project_id,),
            ).fetchall()
            if r["v_key"]
        }
        project_row = conn.execute(
            "SELECT qc_state FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        qc_state = project_row["qc_state"] if project_row else None
        error_video_ids = {
            r["video_id"]
            for r in conn.execute(
                "SELECT DISTINCT video_id FROM qc_issues "
                "WHERE project_id=? AND severity='error'",
                (project_id,),
            ).fetchall()
        }

    scripts_by_video: dict[tuple[str, int | None], dict] = {}
    for row in script_rows:
        if row.get("video_id") is not None:
            scripts_by_video[("id", row["video_id"])] = row
        if row.get("v_key"):
            scripts_by_video[("key", row["v_key"])] = row

    result: list[dict[str, Any]] = []
    for video in videos:
        video_id = video.get("id")
        key = video["key"]
        script = scripts_by_video.get(("id", video_id)) or scripts_by_video.get(("key", key))
        script_id = script["id"] if script else None
        scenes_n = scene_counts.get(script_id, 0) if script_id else 0
        scripts_done = bool(script and (script.get("body_full") or "").strip())
        scenes_done = scripts_done and scenes_n > 0
        qc_done = _qc_done_for_video(qc_state, video_id, error_video_ids)
        result.append({
            "id": video_id,
            "key": key,
            "name": video.get("name") or key,
            "script_type": video.get("script_type"),
            "stages": {
                "scripts": scripts_done,
                "scenes": scenes_done,
                "metadata": key in metadata_keys,
                "thumbnails": key in thumbnail_keys,
                "qc": qc_done,
            },
        })
    return result


def _qc_done_for_video(
    qc_state: str | None,
    video_id: int | None,
    error_video_ids: set[int | None],
) -> bool:
    """QC listo para un video concreto.

    - ``skipped``: el usuario saltó el análisis → listo para todos.
    - ``analyzed``: listo si no hay issues de error que afecten a este
      video (los errores de proyecto ``video_id=None`` bloquean todos).
    - ``None`` (u otro): pendiente.
    """
    if qc_state == "skipped":
        return True
    if qc_state != "analyzed":
        return False
    if None in error_video_ids:
        return False
    return video_id not in error_video_ids


def stage_breakdown_for(project_id: int, stage_key: str) -> list[dict[str, Any]]:
    """Detalle por video para alimentar el stepper y la Hoja de ruta.

    Devuelve entradas ``{id, key, name, done, stage_key}``; ``stage_key``
    se preserva para que ``attach_breakdown_urls`` sepa a qué página
    apuntar sin que el caller tenga que pasarla de nuevo.
    """
    videos = video_stage_status(project_id)
    items: list[dict[str, Any]] = []
    for video in videos:
        items.append({
            "id": video["id"],
            "key": video["key"],
            "name": video["name"],
            "done": video["stages"].get(stage_key, False),
            "stage_key": stage_key,
        })
    return items


def attach_breakdown_urls(project_id: int, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Añade ``url`` por item usando ``item["stage_key"]``.

    No-op si no hay contexto de Flask (tests, CLI): los items siguen
    siendo utilizables para status y nombres.
    """
    from flask import has_app_context
    if not has_app_context():
        return items
    for item in items:
        if item.get("url"):
            continue
        stage_key = item.get("stage_key") or ""
        item["url"] = _stage_url(project_id, stage_key, item.get("id"))
    return items

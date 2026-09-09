"""Blueprint `profiles`: gestion de perfiles reutilizables y de sus etapas (roadmap).

Rutas:
- GET/POST /profiles  — listado, creacion, edicion, borrado y cambio
  del perfil por defecto, mas CRUD de las ``roadmap_stages`` del
  perfil. Las acciones se discriminan por el campo ``action`` del form
  (``create`` / ``set_default`` / ``update`` / ``delete`` /
  ``update_stage`` / ``add_stage`` / ``delete_stage``).

Misma convencion que el resto de blueprints: las funciones de dominio
y constantes (``get_db``, ``now_iso``, ``CONFIG``,
``_roadmap_instruction_for``, ``sync_project_folder``,
``sync_project_stages_for_project``) se importan con local import
dentro del handler para evitar ciclos con app.py.
"""

from __future__ import annotations

import json

from flask import Blueprint, flash, redirect, render_template, request, url_for

profiles_bp = Blueprint("profiles", __name__, url_prefix="/profiles")


def _parse_int_field(name: str, default: int) -> int:
    raw = request.form.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


@profiles_bp.route("/", methods=["GET", "POST"], strict_slashes=False)
def view():
    from app import (
        CONFIG,
        DEFAULT_ROADMAP_STAGES,
        get_db,
        log,
        now_iso,
        sync_project_folder,
        sync_project_stages_for_project,
    )
    from app import _roadmap_instruction_for

    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            platforms = request.form.getlist("platforms")
            now = now_iso()
            with get_db() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO profiles (name, content_type, audience, tone, style,
                        mystery_level, drama_level, narration_speed, platforms, notes,
                        is_default, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        request.form.get("name", "").strip(),
                        request.form.get("content_type", "").strip(),
                        request.form.get("audience", "").strip(),
                        request.form.get("tone", "").strip(),
                        request.form.get("style", "").strip(),
                        _parse_int_field("mystery_level", 5),
                        _parse_int_field("drama_level", 5),
                        _parse_int_field("narration_speed", 150),
                        json.dumps(platforms),
                        request.form.get("notes", "").strip(),
                        1 if request.form.get("is_default") else 0,
                        now,
                    ),
                )
                profile_id = cur.lastrowid
                for idx, stage_name in enumerate(DEFAULT_ROADMAP_STAGES):
                    conn.execute(
                        """
                        INSERT INTO roadmap_stages
                            (profile_id, name, instruction, sort_order, is_active,
                             created_at, updated_at)
                        VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                        (
                            profile_id,
                            stage_name,
                            _roadmap_instruction_for(conn, profile_id, stage_name),
                            idx,
                            now,
                            now,
                        ),
                    )
            flash("Perfil creado", "ok")
        elif action == "set_default":
            pid = request.form.get("profile_id")
            with get_db() as conn:
                conn.execute("UPDATE profiles SET is_default=0")
                conn.execute("UPDATE profiles SET is_default=1 WHERE id=?", (pid,))
        elif action == "update":
            pid = request.form.get("profile_id")
            name = request.form.get("name", "").strip()
            if not pid:
                flash("Falta el perfil a actualizar", "error")
                return redirect(url_for("profiles.view"))
            if not name:
                flash("El nombre del perfil es obligatorio", "error")
                return redirect(url_for("profiles.view"))
            platforms = request.form.getlist("platforms")
            make_default = bool(request.form.get("is_default"))
            with get_db() as conn:
                if make_default:
                    conn.execute("UPDATE profiles SET is_default=0")
                conn.execute(
                    """
                    UPDATE profiles SET
                        name = ?,
                        content_type = ?,
                        audience = ?,
                        tone = ?,
                        style = ?,
                        mystery_level = ?,
                        drama_level = ?,
                        narration_speed = ?,
                        platforms = ?,
                        notes = ?,
                        is_default = ?
                    WHERE id = ?
                """,
                    (
                        name,
                        request.form.get("content_type", "").strip(),
                        request.form.get("audience", "").strip(),
                        request.form.get("tone", "").strip(),
                        request.form.get("style", "").strip(),
                        _parse_int_field("mystery_level", 5),
                        _parse_int_field("drama_level", 5),
                        _parse_int_field("narration_speed", 150),
                        json.dumps(platforms),
                        request.form.get("notes", "").strip(),
                        1 if make_default else 0,
                        pid,
                    ),
                )
            flash("Perfil actualizado", "ok")
        elif action == "delete":
            pid = request.form.get("profile_id")
            with get_db() as conn:
                conn.execute("DELETE FROM profiles WHERE id=?", (pid,))
        elif action == "update_stage":
            profile_id = request.form.get("profile_id")
            stage_id = request.form.get("stage_id")
            name = request.form.get("name", "").strip()
            if not profile_id or not stage_id or not name:
                flash("Faltan datos de la etapa", "error")
                return redirect(url_for("profiles.view"))
            order = _parse_int_field("order", 0)
            instruction = request.form.get("instruction", "")
            is_active = 1 if request.form.get("active") else 0
            now = now_iso()
            with get_db() as conn:
                cur = conn.execute(
                    """
                    UPDATE roadmap_stages
                    SET name=?, instruction=?, sort_order=?, is_active=?, updated_at=?
                    WHERE id=? AND profile_id=?
                """,
                    (name, instruction, order, is_active, now, stage_id, profile_id),
                )
                if cur.rowcount == 0:
                    flash("Etapa no encontrada en el perfil", "error")
                    return redirect(url_for("profiles.view"))
                project_ids = [
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM projects WHERE profile_id=?",
                        (profile_id,),
                    ).fetchall()
                ]
            for pid in project_ids:
                try:
                    sync_project_stages_for_project(pid)
                except Exception:
                    log.exception("[update_stage] sync_project_stages pid=%s", pid)
                try:
                    sync_project_folder(pid)
                except Exception:
                    log.exception("[update_stage] sync_project_folder pid=%s", pid)
        elif action == "add_stage":
            profile_id = request.form.get("profile_id")
            name = request.form.get("name", "").strip()
            if not profile_id or not name:
                flash("Falta perfil o nombre de etapa", "error")
                return redirect(url_for("profiles.view"))
            order = _parse_int_field("order", 0)
            instruction = request.form.get("instruction", "")
            is_active = 1 if request.form.get("active") else 0
            now = now_iso()
            with get_db() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO roadmap_stages
                        (profile_id, name, instruction, sort_order, is_active,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (profile_id, name, instruction, order, is_active, now, now),
                )
                new_stage_id = cur.lastrowid
                project_ids = [
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM projects WHERE profile_id=?",
                        (profile_id,),
                    ).fetchall()
                ]
                if is_active:
                    for pid in project_ids:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO project_stages
                                (project_id, roadmap_stage_id, instruction,
                                 response, updated_at)
                            VALUES (?, ?, ?, '', ?)
                        """,
                            (pid, new_stage_id, instruction, now),
                        )
            for pid in project_ids:
                try:
                    sync_project_stages_for_project(pid)
                except Exception:
                    log.exception("[add_stage] sync_project_stages pid=%s", pid)
                try:
                    sync_project_folder(pid)
                except Exception:
                    log.exception("[add_stage] sync_project_folder pid=%s", pid)
        elif action == "delete_stage":
            profile_id = request.form.get("profile_id")
            stage_id = request.form.get("stage_id")
            if not profile_id or not stage_id:
                flash("Faltan datos de la etapa", "error")
                return redirect(url_for("profiles.view"))
            with get_db() as conn:
                owned = conn.execute(
                    "SELECT 1 FROM roadmap_stages WHERE id=? AND profile_id=?",
                    (stage_id, profile_id),
                ).fetchone()
                if not owned:
                    flash("Etapa no encontrada en el perfil", "error")
                    return redirect(url_for("profiles.view"))
                project_ids = [
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM projects WHERE profile_id=?",
                        (profile_id,),
                    ).fetchall()
                ]
                conn.execute("DELETE FROM roadmap_stages WHERE id=?", (stage_id,))
            for pid in project_ids:
                try:
                    sync_project_stages_for_project(pid)
                except Exception:
                    log.exception("[delete_stage] sync_project_stages pid=%s", pid)
                try:
                    sync_project_folder(pid)
                except Exception:
                    log.exception("[delete_stage] sync_project_folder pid=%s", pid)
        return redirect(url_for("profiles.view"))

    with get_db() as conn:
        profiles_list = [
            dict(r) for r in conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()
        ]
        stages_by_profile: dict[int, list[dict]] = {}
        if profiles_list:
            ids = [p["id"] for p in profiles_list]
            placeholders = ",".join("?" for _ in ids)
            for r in conn.execute(
                f"""
                SELECT id, profile_id, name, instruction, sort_order, is_active
                FROM roadmap_stages
                WHERE profile_id IN ({placeholders})
                ORDER BY sort_order, id
            """,
                ids,
            ).fetchall():
                stages_by_profile.setdefault(r["profile_id"], []).append(dict(r))
    for p in profiles_list:
        try:
            p["platforms_list"] = json.loads(p.get("platforms") or "[]")
        except Exception as e:
            log.debug("platforms no parseable en perfil %s: %s", p.get("id"), e)
            p["platforms_list"] = []
        p["stages"] = [
            {
                "id": s["id"],
                "name": s["name"],
                "instruction": s["instruction"],
                "order": s["sort_order"],
                "active": bool(s["is_active"]),
            }
            for s in stages_by_profile.get(p["id"], [])
        ]
    return render_template("profiles.html", profiles=profiles_list, config=CONFIG)
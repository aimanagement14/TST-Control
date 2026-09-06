"""Blueprint `profiles`: gestion de perfiles reutilizables.

Rutas:
- GET/POST /profiles  — listado, creacion, edicion, borrado y cambio
  del perfil por defecto. Las acciones se discriminan por el campo
  ``action`` del form (``create`` / ``set_default`` / ``update`` /
  ``delete``).

Misma convencion que el resto de blueprints: las funciones de dominio
y constantes (``get_db``, ``now_iso``, ``CONFIG``) se importan con
local import dentro del handler para evitar ciclos con app.py.
"""
from __future__ import annotations

import json

from flask import Blueprint, flash, redirect, render_template, request, url_for

profiles_bp = Blueprint("profiles", __name__, url_prefix="/profiles")


@profiles_bp.route("/", methods=["GET", "POST"], strict_slashes=False)
def view():
    from app import CONFIG, get_db, log, now_iso

    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            platforms = request.form.getlist("platforms")
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO profiles (name, content_type, audience, tone, style,
                        mystery_level, drama_level, narration_speed, platforms, notes,
                        is_default, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    request.form.get("name", "").strip(),
                    request.form.get("content_type", "").strip(),
                    request.form.get("audience", "").strip(),
                    request.form.get("tone", "").strip(),
                    request.form.get("style", "").strip(),
                    int(request.form.get("mystery_level", 5)),
                    int(request.form.get("drama_level", 5)),
                    int(request.form.get("narration_speed", 150)),
                    json.dumps(platforms),
                    request.form.get("notes", "").strip(),
                    1 if request.form.get("is_default") else 0,
                    now_iso(),
                ))
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
                conn.execute("""
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
                """, (
                    name,
                    request.form.get("content_type", "").strip(),
                    request.form.get("audience", "").strip(),
                    request.form.get("tone", "").strip(),
                    request.form.get("style", "").strip(),
                    int(request.form.get("mystery_level", 5)),
                    int(request.form.get("drama_level", 5)),
                    int(request.form.get("narration_speed", 150)),
                    json.dumps(platforms),
                    request.form.get("notes", "").strip(),
                    1 if make_default else 0,
                    pid,
                ))
            flash("Perfil actualizado", "ok")
        elif action == "delete":
            pid = request.form.get("profile_id")
            with get_db() as conn:
                conn.execute("DELETE FROM profiles WHERE id=?", (pid,))
        return redirect(url_for("profiles.view"))

    with get_db() as conn:
        profiles_list = [dict(r) for r in conn.execute(
            "SELECT * FROM profiles ORDER BY name"
        ).fetchall()]
    for p in profiles_list:
        try:
            p["platforms_list"] = json.loads(p.get("platforms") or "[]")
        except Exception as e:
            # expected: platforms puede ser un string legacy; caemos a
            # lista vacía y el formulario se renderiza sin opciones.
            log.debug("platforms no parseable en perfil %s: %s", p.get("id"), e)
            p["platforms_list"] = []
    return render_template("profiles.html", profiles=profiles_list, config=CONFIG)
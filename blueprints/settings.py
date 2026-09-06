"""Blueprint `settings`: configuracion global (LLM, presets, providers).

Rutas:
- GET/POST /settings  — render del formulario y guardado de la
  configuracion global o de presets individuales. Las acciones se
  discriminan por el campo ``action`` del form (``save_preset`` /
  ``delete_preset`` / ``activate_preset`` / ``save`` por defecto).

Misma convencion que el resto de blueprints: ``CONFIG`` y
``CONFIG_PATH`` se importan con local import dentro del handler para
evitar ciclos con app.py.
"""
from __future__ import annotations

import json

from flask import Blueprint, flash, redirect, render_template, request, url_for

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


@settings_bp.route("/", methods=["GET", "POST"], strict_slashes=False)
def view():
    from app import CONFIG, CONFIG_PATH

    if request.method == "POST":
        action = request.form.get("action", "save")

        if action == "save_preset" and request.form.get("preset_key"):
            key = request.form.get("preset_key").strip()
            if not key:
                flash("Nombre del preset vacío", "error")
                return redirect(url_for("settings.view"))
            CONFIG["llm"].setdefault("presets", {})
            # Eliminar _comment si se reescribe
            CONFIG["llm"]["presets"].pop("_comment", None)
            existing = CONFIG["llm"]["presets"].get(key, {})
            CONFIG["llm"]["presets"][key] = {
                "label": request.form.get("label", key).strip() or key,
                "type": request.form.get("type", "openai"),
                "api_key": request.form.get("api_key", existing.get("api_key", "")).strip(),
                "base_url": request.form.get("base_url", existing.get("base_url", "")).strip(),
                "model": request.form.get("model", existing.get("model", "")).strip(),
                "notes": request.form.get("notes", "").strip(),
            }
            flash(f"Preset «{key}» guardado", "ok")

        elif action == "delete_preset":
            key = request.form.get("preset_key", "").strip()
            if key and key in CONFIG["llm"].get("presets", {}):
                del CONFIG["llm"]["presets"][key]
                if CONFIG["llm"].get("active_preset") == key:
                    CONFIG["llm"]["active_preset"] = None
                flash(f"Preset «{key}» eliminado", "ok")

        elif action == "activate_preset":
            key = request.form.get("preset_key", "").strip()
            if key and key in CONFIG["llm"].get("presets", {}):
                CONFIG["llm"]["active_preset"] = key
                preset_type = CONFIG["llm"]["presets"][key].get("type", "openai")
                if preset_type == "anthropic":
                    CONFIG["llm"]["provider"] = "anthropic"
                else:
                    CONFIG["llm"]["provider"] = "openai"
                flash(f"Preset «{key}» activado. El provider se ha ajustado.", "ok")
            else:
                flash("Preset no encontrado", "error")

        else:
            CONFIG["llm"]["provider"] = request.form.get("provider", "manual")
            CONFIG["llm"]["openai"]["api_key"] = request.form.get("openai_key", "").strip()
            CONFIG["llm"]["openai"]["model"] = request.form.get("openai_model", "gpt-4o-mini").strip()
            CONFIG["llm"]["openai"]["base_url"] = request.form.get(
                "openai_base", "https://api.openai.com/v1"
            ).strip()
            CONFIG["llm"]["anthropic"]["api_key"] = request.form.get("anthropic_key", "").strip()
            CONFIG["llm"]["anthropic"]["model"] = request.form.get(
                "anthropic_model", "claude-3-5-sonnet-20241022"
            ).strip()
            flash("Configuración guardada", "ok")

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f, ensure_ascii=False, indent=2)
        return redirect(url_for("settings.view"))

    presets = {
        k: v for k, v in CONFIG["llm"].get("presets", {}).items() if not k.startswith("_")
    }
    return render_template("settings.html", config=CONFIG, presets=presets)
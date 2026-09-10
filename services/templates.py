"""Mini-motor de plantillas ``{{ path.to.value }}``.

Pensado exclusivamente para los prompts SYS/USER del pipeline. No es un
motor de propósito general: solo soporta sustitución por paths con punto
contra un dict, sin lógica, sin condicionales, sin escapes. La idea es
que un perfil pueda inyectarse en un prompt sin tener que reescribirlo.

API:
- ``render(text, context)``: sustituye ``{{a.b.c}}`` por ``context["a"]["b"]["c"]``.
- ``render_profile(text, profile)``: shortcut que monta el contexto con
  las claves del perfil (mystery_level, drama_level, tone, style,
  audience, narration_speed, platforms, content_type) más una sección
  `app` con datos globales del proyecto.

Paths desconocidos o fallidos se sustituyen por cadena vacía y se
registran en un set que el caller puede inspeccionar vía
``RenderReport.unknown`` si quiere diagnosticar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s*\}\}")


@dataclass
class RenderReport:
    """Resumen de una operación de render."""

    unknown: set[str] = field(default_factory=set)


def _lookup(context: dict[str, Any], path: str) -> tuple[bool, str]:
    """Resuelve ``path`` (con puntos) contra ``context``.

    Devuelve ``(encontrado, valor)``. Si el path no existe devuelve
    ``(False, "")``.
    """
    node: Any = context
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
            continue
        return False, ""
    if isinstance(node, (str, int, float, bool)):
        return True, str(node)
    return False, ""


def render(text: str, context: dict[str, Any]) -> tuple[str, RenderReport]:
    """Sustituye cada ``{{path}}`` por su valor en ``context``."""
    if not text:
        return text or "", RenderReport()
    report = RenderReport()

    def _sub(match: re.Match[str]) -> str:
        path = match.group(1)
        ok, value = _lookup(context, path)
        if not ok:
            report.unknown.add(path)
            return ""
        return value

    return _TEMPLATE_RE.sub(_sub, text), report


def _normalize_platforms(raw: Any) -> list[str]:
    """Acepta JSON array, string separado por comas o ya-lista."""
    if isinstance(raw, list):
        return [str(p) for p in raw]
    if not raw:
        return []
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            import json
            data = json.loads(text)
            if isinstance(data, list):
                return [str(p) for p in data]
        except Exception:
            pass
    return [p.strip() for p in text.split(",") if p.strip()]


def profile_context(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Construye el sub-dict ``profile.*`` desde una fila de la tabla ``profiles``."""
    p = profile or {}
    platforms = _normalize_platforms(p.get("platforms"))
    return {
        "id": p.get("id"),
        "name": p.get("name") or "",
        "content_type": p.get("content_type") or "documental",
        "audience": p.get("audience") or "",
        "tone": p.get("tone") or "serio",
        "style": p.get("style") or "cinematográfico",
        "mystery_level": p.get("mystery_level") if p.get("mystery_level") is not None else 7,
        "drama_level": p.get("drama_level") if p.get("drama_level") is not None else 6,
        "narration_speed": p.get("narration_speed") if p.get("narration_speed") else 150,
        "platforms": platforms,
        "platforms_csv": ", ".join(platforms) if platforms else "no definidas",
    }


def app_context() -> dict[str, Any]:
    """Sub-dict ``app.*`` con datos estáticos (canal, marca)."""
    app_cfg: dict[str, Any] = {}
    visual_style_keywords: str = ""
    try:
        from app import CONFIG
        app_cfg = CONFIG.get("app", {}) or {}
        visual_style_keywords = (CONFIG.get("visual_style", {}) or {}).get("keywords", "") or ""
    except Exception:
        pass
    return {
        "name": app_cfg.get("name") or "Todo Sobre Todo",
        "tagline": app_cfg.get("tagline") or "",
        "version": app_cfg.get("version") or "",
        "visual_style_keywords": visual_style_keywords,
    }


def render_profile(text: str, profile: dict[str, Any] | None) -> tuple[str, RenderReport]:
    """Shortcut: monta el contexto de perfil+app y aplica ``render``."""
    context = {
        "profile": profile_context(profile),
        "app": app_context(),
    }
    return render(text, context)

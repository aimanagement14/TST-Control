"""
Todo Sobre Todo — Centro de producción de contenido
Aplicación Flask minimalista para preparar contenido antes de producción.

Arquitectura deliberadamente simple:
- Un solo archivo de aplicación
- SQLite sin ORM (más transparente)
- LLM opcional (manual por defecto, sin costos ni dependencias)
- Plantillas Jinja2
"""

import os
import re
import json
import sqlite3
import urllib.request
import zipfile
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, send_from_directory, abort, session
)

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = BASE_DIR / "config.json"
DB_PATH = BASE_DIR / "workflow.db"
PROJECTS_DIR = BASE_DIR / "projects"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

PROJECTS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = CONFIG["app"]["secret_key"]
app.config["JSON_AS_ASCII"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(STATIC_DIR, "favicon.ico", mimetype="image/x-icon")

# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    content_type TEXT,
    audience TEXT,
    tone TEXT,
    style TEXT,
    mystery_level INTEGER DEFAULT 5,
    drama_level INTEGER DEFAULT 5,
    narration_speed INTEGER DEFAULT 150,
    platforms TEXT,
    notes TEXT,
    is_default INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    topic TEXT,
    profile_id INTEGER,
    status TEXT DEFAULT 'created',
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);

CREATE TABLE IF NOT EXISTS research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER UNIQUE,
    content TEXT,
    sources TEXT,
    facts TEXT,
    theories TEXT,
    unverified TEXT,
    updated_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS concept (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER UNIQUE,
    angle TEXT,
    thesis TEXT,
    key_points TEXT,
    emotional_hook TEXT,
    what_they_learn TEXT,
    what_they_feel TEXT,
    risks TEXT,
    updated_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    type TEXT,
    title TEXT,
    hook TEXT,
    context TEXT,
    development TEXT,
    revelations TEXT,
    conclusion TEXT,
    cta TEXT,
    body_full TEXT,
    structure_json TEXT,
    word_count INTEGER DEFAULT 0,
    updated_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    script_id INTEGER,
    scene_number INTEGER,
    narration TEXT,
    visual_description TEXT,
    camera_movement TEXT,
    transition TEXT,
    duration_seconds INTEGER DEFAULT 0,
    updated_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    scene_id INTEGER,
    subject TEXT,
    environment TEXT,
    era TEXT,
    lighting TEXT,
    camera TEXT,
    composition TEXT,
    atmosphere TEXT,
    style TEXT,
    full_prompt_en TEXT,
    full_prompt_es TEXT,
    updated_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS metadata_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    platform TEXT,
    titles TEXT,
    description TEXT,
    chapters TEXT,
    tags TEXT,
    hashtags TEXT,
    caption TEXT,
    hook TEXT,
    cta TEXT,
    on_screen_text TEXT,
    updated_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS thumbnail_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    script_type TEXT,
    prompt TEXT,
    updated_at TEXT,
    UNIQUE(project_id, script_type),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qc_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    stage TEXT,
    severity TEXT,
    message TEXT,
    field TEXT,
    resolved INTEGER DEFAULT 0,
    created_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS stage_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    stage TEXT,
    sys_prompt TEXT,
    user_prompt TEXT,
    updated_at TEXT,
    UNIQUE(project_id, stage),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_db():
    """Obtiene una conexión nueva a la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Inicializa el esquema y los datos por defecto."""
    with get_db() as conn:
        conn.executescript(SCHEMA)
        # Perfil por defecto si no existe ninguno
        cur = conn.execute("SELECT COUNT(*) AS n FROM profiles")
        if cur.fetchone()["n"] == 0:
            now = datetime.now().isoformat()
            conn.execute("""
                INSERT INTO profiles
                (name, content_type, audience, tone, style, mystery_level,
                 drama_level, narration_speed, platforms, is_default, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                "Todo Sobre Todo / Misterio",
                "Documental de misterio",
                "Curiosos, aficionados a lo alternativo, 25-55 años",
                "Serio con toques intrigantes, narrativo",
                "Cinematográfico, contrastado, con toques conspiranoicos",
                7, 6, 150,
                json.dumps(["youtube", "shorts", "tiktok", "instagram", "facebook"]),
                now,
            ))


init_db()


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def count_words(text):
    if not text:
        return 0
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def estimate_duration_seconds(text, wpm=150):
    """Estima la duración de narración en segundos según palabras por minuto."""
    words = count_words(text)
    if wpm <= 0:
        wpm = 150
    return int(round(words / wpm * 60))


def project_stage_status(project):
    """Devuelve un dict con el estado de cada etapa del proyecto."""
    qc_cfg = CONFIG["qc"]["checks"]
    min_scenes_long = qc_cfg["min_scenes_long"]
    min_scenes_short = qc_cfg["min_scenes_short"]
    with get_db() as conn:
        stages = {
            "research": conn.execute(
                "SELECT COUNT(*) AS n FROM research WHERE project_id=? AND content IS NOT NULL AND content != ''",
                (project["id"],)
            ).fetchone()["n"] > 0,
            "concept": conn.execute(
                "SELECT COUNT(*) AS n FROM concept WHERE project_id=? AND angle IS NOT NULL AND angle != ''",
                (project["id"],)
            ).fetchone()["n"] > 0,
            "scripts_long": conn.execute(
                "SELECT COUNT(*) AS n FROM scripts WHERE project_id=? AND type='long'",
                (project["id"],)
            ).fetchone()["n"] > 0,
            "scripts_short": conn.execute(
                "SELECT COUNT(*) AS n FROM scripts WHERE project_id=? AND type='short'",
                (project["id"],)
            ).fetchone()["n"] > 0,
        }
        scripts = [dict(r) for r in conn.execute(
            "SELECT id, type FROM scripts WHERE project_id=?", (project["id"],),
        ).fetchall()]
        scenes_done = False
        if scripts:
            scenes_done = True
            for s in scripts:
                min_n = min_scenes_long if s["type"] == "long" else min_scenes_short
                count = conn.execute(
                    "SELECT COUNT(*) AS n FROM scenes WHERE project_id=? AND script_id=?",
                    (project["id"], s["id"]),
                ).fetchone()["n"]
                if count < min_n:
                    scenes_done = False
                    break
        stages["scenes"] = scenes_done
        stages["metadata"] = conn.execute(
            "SELECT COUNT(*) AS n FROM metadata_records WHERE project_id=?",
            (project["id"],)
        ).fetchone()["n"] > 0
        thumb_long = conn.execute(
            "SELECT prompt FROM thumbnail_records WHERE project_id=? AND script_type='long'",
            (project["id"],),
        ).fetchone()
        thumb_short = conn.execute(
            "SELECT prompt FROM thumbnail_records WHERE project_id=? AND script_type='short'",
            (project["id"],),
        ).fetchone()
        stages["thumbnails"] = bool(
            thumb_long and thumb_long["prompt"] and
            thumb_short and thumb_short["prompt"]
        )
    return stages


# ---------------------------------------------------------------------------
# Pipeline: orden de etapas, estado legible y siguiente acción
# ---------------------------------------------------------------------------

PIPELINE_STAGES = (
    {"key": "research", "num": "01", "label": "Investigación", "short": "Investigación",
     "endpoint": "research", "hint": "Hechos, fuentes y teorías"},
    {"key": "concept", "num": "02", "label": "Concepto", "short": "Concepto",
     "endpoint": "concept", "hint": "Ángulo, tesis y gancho"},
    {"key": "scripts_long", "num": "03", "label": "Guion 5 min", "short": "Guion 5 min",
     "endpoint": "scripts", "hint": "Documental completo"},
    {"key": "scripts_short", "num": "04", "label": "Guion 1 min", "short": "Guion 1 min",
     "endpoint": "scripts", "hint": "Versión vertical"},
    {"key": "scenes", "num": "05", "label": "Escenas", "short": "Escenas",
     "endpoint": "scenes", "hint": "Secuencia visual"},
    {"key": "metadata", "num": "06", "label": "Metadata", "short": "Metadata",
     "endpoint": "metadata", "hint": "Títulos, tags y CTA"},
    {"key": "thumbnails", "num": "07", "label": "Miniaturas", "short": "Miniaturas",
     "endpoint": "thumbnails", "hint": "Prompts visuales de portada"},
    {"key": "qc", "num": "08", "label": "Control de calidad", "short": "Calidad",
     "endpoint": "qc", "hint": "Revisión antes de exportar"},
)

PAGE_ORDER = ("research", "concept", "scripts", "scenes",
              "metadata", "thumbnails", "qc", "export")

PAGE_LABELS = {
    "research": "Investigación",
    "concept": "Concepto",
    "scripts": "Guiones",
    "scenes": "Escenas",
    "metadata": "Metadata",
    "thumbnails": "Miniaturas",
    "qc": "Control de calidad",
    "export": "Exportar",
}

STATUS_LABELS = {
    "created": "Sin empezar",
    "research": "En investigación",
    "concept": "En concepto",
    "scripts": "En guion",
    "scenes": "En escenas",
    "metadata": "En metadata",
    "thumbnails": "En miniaturas",
    "ready": "Listo para exportar",
}


def status_label(status):
    """Traduce el estado interno del proyecto a lenguaje de usuario."""
    return STATUS_LABELS.get(status, status or "—")


def format_timecode(seconds):
    """Segundos a MM:SS, el formato con el que se mide un vídeo."""
    total = max(0, int(seconds or 0))
    return f"{total // 60:02d}:{total % 60:02d}"


def project_runtime(project, profile=None):
    """Duración estimada del guion largo frente al objetivo del formato."""
    checks = CONFIG["qc"]["checks"]
    wpm = (profile or {}).get("narration_speed") or checks["default_wpm"]
    target = checks["target_duration_long_seconds"]
    with get_db() as conn:
        row = conn.execute(
            "SELECT word_count FROM scripts WHERE project_id=? AND type='long'",
            (project["id"],),
        ).fetchone()
    words = (row["word_count"] if row else 0) or 0
    seconds = int(round(words / wpm * 60)) if words else 0
    return {
        "words": words,
        "seconds": seconds,
        "target": target,
        "timecode": format_timecode(seconds),
        "target_timecode": format_timecode(target),
        "percent": min(100, round(seconds * 100 / target)) if target else 0,
        "over": bool(target and seconds > target * 1.1),
        "has_script": words > 0,
    }


def pipeline_view(project, current=None):
    """Estado del pipeline para la barra de etapas y el paso siguiente.

    `current` es el nombre de la página activa (endpoint), no la etapa:
    la página de guiones cubre dos etapas del pipeline.
    """
    stages = dict(project.get("stages") or project_stage_status(project))
    qc_done = project.get("status") == "ready"
    if not qc_done:
        with get_db() as conn:
            n_qc = conn.execute(
                "SELECT COUNT(*) AS n FROM qc_issues WHERE project_id=?",
                (project["id"],),
            ).fetchone()["n"]
            qc_done = n_qc > 0
    stages["qc"] = qc_done

    cells, pending = [], None
    for stage in PIPELINE_STAGES:
        cell = dict(
            stage,
            done=bool(stages.get(stage["key"])),
            current=stage["endpoint"] == current,
            url=url_for(stage["endpoint"], project_id=project["id"]),
        )
        if not cell["done"] and pending is None:
            pending = cell
        cells.append(cell)

    done = sum(1 for c in cells if c["done"])
    index = PAGE_ORDER.index(current) if current in PAGE_ORDER else None

    def step(offset):
        if index is None:
            return None
        pos = index + offset
        if not 0 <= pos < len(PAGE_ORDER):
            return None
        page = PAGE_ORDER[pos]
        return {"label": PAGE_LABELS[page],
                "url": url_for(page, project_id=project["id"])}

    return {
        "cells": cells,
        "done": done,
        "total": len(cells),
        "percent": round(done * 100 / len(cells)),
        "next": pending,
        "prev_step": step(-1),
        "next_step": step(1),
        "complete": done == len(cells),
        "runtime": project_runtime(project, get_profile(project.get("profile_id"))),
    }


def get_or_create_research(project_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM research WHERE project_id=?", (project_id,)).fetchone()
        if row:
            return dict(row)
        conn.execute(
            "INSERT INTO research (project_id, updated_at) VALUES (?, ?)",
            (project_id, now_iso())
        )
        row = conn.execute("SELECT * FROM research WHERE project_id=?", (project_id,)).fetchone()
        return dict(row) if row else {"project_id": project_id}


def get_or_create_concept(project_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM concept WHERE project_id=?", (project_id,)).fetchone()
        if row:
            return dict(row)
        conn.execute(
            "INSERT INTO concept (project_id, updated_at) VALUES (?, ?)",
            (project_id, now_iso())
        )
        row = conn.execute("SELECT * FROM concept WHERE project_id=?", (project_id,)).fetchone()
        return dict(row) if row else {"project_id": project_id}


def get_script(project_id, script_type):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM scripts WHERE project_id=? AND type=?",
            (project_id, script_type)
        ).fetchone()
        return dict(row) if row else None


def get_profile(profile_id):
    if not profile_id:
        return None
    with get_db() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        return dict(row) if row else None


def get_default_profile():
    with get_db() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE is_default=1 LIMIT 1").fetchone()
        if row:
            return dict(row)
        row = conn.execute("SELECT * FROM profiles LIMIT 1").fetchone()
        return dict(row) if row else None


def fetch_project_or_404(project_id):
    """Carga un proyecto o aborta con 404."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            abort(404)
        return dict(row)


def fetch_optional_dict(conn, sql, params=()):
    """Ejecuta una consulta y devuelve dict o {} si no hay fila."""
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else {}


def get_saved_prompt(project_id, stage):
    """Recupera el prompt guardado para una etapa, o None."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM stage_prompts WHERE project_id=? AND stage=?",
            (project_id, stage),
        ).fetchone()
        return dict(row) if row else None


def save_stage_prompt(project_id, stage, sys_prompt, user_prompt):
    """Guarda (o actualiza) el prompt de una etapa en el proyecto."""
    now = now_iso()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM stage_prompts WHERE project_id=? AND stage=?",
            (project_id, stage),
        ).fetchone()
        if existing:
            conn.execute("""
                UPDATE stage_prompts SET sys_prompt=?, user_prompt=?, updated_at=?
                WHERE id=?
            """, (sys_prompt, user_prompt, now, existing["id"]))
        else:
            conn.execute("""
                INSERT INTO stage_prompts (project_id, stage, sys_prompt, user_prompt, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (project_id, stage, sys_prompt, user_prompt, now))


def list_saved_prompts(project_id):
    """Devuelve todos los prompts guardados del proyecto indexados por stage."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM stage_prompts WHERE project_id=? ORDER BY updated_at",
            (project_id,),
        ).fetchall()
    return {row["stage"]: dict(row) for row in rows}


# ---------------------------------------------------------------------------
# Auto-prompt: garantiza que siempre quede un prompt guardado por etapa
# ---------------------------------------------------------------------------

_STAGE_BUILDERS = {
    "research": lambda proj, prof, ctx: build_research_prompt(proj, prof),
    "concept": lambda proj, prof, ctx: build_concept_prompt(
        proj, prof, ctx.get("research") or {},
    ),
    "script_long": lambda proj, prof, ctx: build_script_prompt(
        proj, prof, ctx.get("research") or {}, ctx.get("concept") or {}, "long",
    ),
    "script_short": lambda proj, prof, ctx: build_script_prompt(
        proj, prof, ctx.get("research") or {}, ctx.get("concept") or {}, "short",
    ),
    "scenes": lambda proj, prof, ctx: build_scenes_prompt(
        proj, prof, ctx.get("script") or {},
    ),
    "metadata_youtube": lambda proj, prof, ctx: build_metadata_prompt(
        proj, prof, ctx.get("script") or {}, "youtube",
    ),
    "metadata_shorts": lambda proj, prof, ctx: build_metadata_prompt(
        proj, prof, ctx.get("script") or {}, "shorts",
    ),
    "thumbnail_long": lambda proj, prof, ctx: build_thumbnail_prompt(
        proj, prof, ctx.get("script") or {}, "long",
    ),
    "thumbnail_short": lambda proj, prof, ctx: build_thumbnail_prompt(
        proj, prof, ctx.get("script") or {}, "short",
    ),
}


def _stage_context(project_id, stage):
    """Carga el contexto necesario para regenerar el prompt de una etapa."""
    ctx = {}
    with get_db() as conn:
        if stage in ("concept", "script_long", "script_short",
                     "scenes", "metadata_youtube", "metadata_shorts"):
            ctx["research"] = fetch_optional_dict(
                conn, "SELECT * FROM research WHERE project_id=?", (project_id,),
            )
        if stage in ("script_long", "script_short", "scenes",
                     "metadata_youtube", "metadata_shorts",
                     "thumbnail_long", "thumbnail_short"):
            ctx["concept"] = fetch_optional_dict(
                conn, "SELECT * FROM concept WHERE project_id=?", (project_id,),
            )
            script_type = "long" if stage in ("script_long", "metadata_youtube", "thumbnail_long") else (
                "short" if stage in ("script_short", "metadata_shorts", "thumbnail_short") else "long"
            )
            ctx["script"] = get_script(project_id, script_type) or {}
    return ctx


def _ensure_stage_prompt(project_id, stage, project, profile, extra_ctx=None):
    """Si no hay prompt guardado para la etapa, genera y guarda el canónico.

    Solo se ejecuta cuando la etapa ya tiene contenido persistido, para no
    guardar prompts de etapas vacías.
    """
    if get_saved_prompt(project_id, stage):
        return False
    with get_db() as conn:
        has_content = False
        if stage == "research":
            has_content = bool(conn.execute(
                "SELECT content FROM research WHERE project_id=?",
                (project_id,),
            ).fetchone()["content"])
        elif stage == "concept":
            row = conn.execute(
                "SELECT angle FROM concept WHERE project_id=?", (project_id,),
            ).fetchone()
            has_content = bool(row and row["angle"])
        elif stage in ("script_long", "script_short"):
            stype = stage.split("_", 1)[1]
            has_content = bool(conn.execute(
                "SELECT id FROM scripts WHERE project_id=? AND type=?",
                (project_id, stype),
            ).fetchone())
        elif stage == "scenes":
            has_content = conn.execute(
                "SELECT COUNT(*) AS n FROM scenes WHERE project_id=?",
                (project_id,),
            ).fetchone()["n"] > 0
        elif stage in ("metadata_youtube", "metadata_shorts"):
            platform = stage.split("_", 1)[1]
            has_content = bool(conn.execute(
                "SELECT id FROM metadata_records WHERE project_id=? AND platform=?",
                (project_id, platform),
            ).fetchone())
        elif stage in ("thumbnail_long", "thumbnail_short"):
            script_type = stage.split("_", 1)[1]
            has_content = bool(conn.execute(
                "SELECT id FROM thumbnail_records WHERE project_id=? AND script_type=?",
                (project_id, script_type),
            ).fetchone())
        else:
            has_content = False
    if not has_content:
        return False
    builder = _STAGE_BUILDERS.get(stage)
    if not builder:
        return False
    ctx = _stage_context(project_id, stage)
    if extra_ctx:
        ctx.update(extra_ctx)
    try:
        sys_p, user_p = builder(project, profile, ctx)
    except Exception:
        return False
    if sys_p and user_p:
        save_stage_prompt(project_id, stage, sys_p, user_p)
        return True
    return False


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

def build_research_prompt(project, profile):
    """Construye el prompt estructurado para la fase de investigación."""
    sys_prompt = CONFIG["prompts"]["research"]["system"]
    fmt = CONFIG["prompts"]["research"]["format"]
    user_msg = (
        f"Tema: {project['topic']}\n"
        f"Canal: Todo Sobre Todo\n"
        f"Tipo de contenido: {profile['content_type'] if profile else 'documental'}\n"
        f"Perfil de misterio: {profile['mystery_level'] if profile else 7}/10\n\n"
        f"Investiga este tema de forma rigurosa y devuelve SIEMPRE en este formato:\n\n{fmt}"
    )
    return sys_prompt, user_msg


def build_concept_prompt(project, profile, research):
    sys_prompt = CONFIG["prompts"]["concept"]["system"]
    fmt = CONFIG["prompts"]["concept"]["format"]
    user_msg = (
        f"Tema: {project['topic']}\n"
        f"Investigación disponible:\n{research.get('content','')[:3000]}\n\n"
        f"Perfil del proyecto:\n"
        f"- Tono: {profile['tone'] if profile else 'serio'}\n"
        f"- Estilo: {profile['style'] if profile else 'cinematográfico'}\n"
        f"- Nivel de misterio: {profile['mystery_level'] if profile else 7}/10\n"
        f"- Nivel de dramatización: {profile['drama_level'] if profile else 6}/10\n\n"
        f"Genera un concepto potente y devuelve SIEMPRE en este formato:\n\n{fmt}"
    )
    return sys_prompt, user_msg


def build_script_prompt(project, profile, research, concept, script_type):
    if script_type == "long":
        sys_prompt = CONFIG["prompts"]["script_long"]["system"]
        fmt = CONFIG["prompts"]["script_long"]["format"]
        duration_txt = "5 minutos"
    else:
        sys_prompt = CONFIG["prompts"]["script_short"]["system"]
        fmt = CONFIG["prompts"]["script_short"]["format"]
        duration_txt = "1 minuto (60-75 segundos)"

    key_points = concept.get("key_points", "")
    if isinstance(key_points, str):
        try:
            key_points = json.loads(key_points)
            if isinstance(key_points, list):
                key_points = "\n".join(f"- {p}" for p in key_points)
        except Exception:
            pass

    user_msg = (
        f"Tema: {project['topic']}\n"
        f"Duración objetivo: {duration_txt}\n"
        f"Ángulo: {concept.get('angle','')}\n"
        f"Tesis: {concept.get('thesis','')}\n"
        f"Puntos clave:\n{key_points or ''}\n\n"
        f"Datos de la investigación:\n{research.get('content','')[:2500]}\n\n"
        f"Tono: {profile['tone'] if profile else 'serio'}\n"
        f"Nivel de misterio: {profile['mystery_level'] if profile else 7}/10\n"
        f"Velocidad narración: {profile['narration_speed'] if profile else 150} ppm\n\n"
        f"Escribe el guion y devuelve SIEMPRE en este formato:\n\n{fmt}"
    )
    return sys_prompt, user_msg


def build_scenes_prompt(project, profile, script):
    sys_prompt = CONFIG["prompts"]["scenes"]["system"]
    fmt = CONFIG["prompts"]["scenes"]["format"]
    user_msg = (
        f"Tema: {project['topic']}\n"
        f"Estilo visual: {profile['style'] if profile else 'cinematográfico'}\n"
        f"Duración total objetivo: {script.get('word_count',0)/(profile['narration_speed'] if profile else 150)*60:.0f} segundos\n\n"
        f"Guion a convertir en escenas:\n{script.get('body_full','')}\n\n"
        f"Devuelve SOLO el JSON con las escenas, en este formato:\n\n{fmt}"
    )
    return sys_prompt, user_msg


def build_metadata_prompt(project, profile, script, platform):
    if platform == "youtube":
        sys_prompt = CONFIG["prompts"]["metadata_youtube"]["system"]
        fmt = CONFIG["prompts"]["metadata_youtube"]["format"]
    else:
        sys_prompt = CONFIG["prompts"]["metadata_shorts"]["system"]
        fmt = CONFIG["prompts"]["metadata_shorts"]["format"]
    platforms_raw = profile["platforms"] if profile else ""
    platforms_list = []
    if platforms_raw:
        try:
            platforms_list = json.loads(platforms_raw)
        except Exception:
            platforms_list = [platforms_raw]
    platforms_txt = ", ".join(platforms_list) if platforms_list else "no definidas"
    user_msg = (
        f"Tema: {project['topic']}\n"
        f"Título del guion: {script.get('title','')}\n"
        f"Hook: {script.get('hook','')}\n"
        f"Tipo de contenido: {profile['content_type'] if profile else ''}\n"
        f"Plataformas objetivo: {platforms_txt}\n\n"
        f"Guion completo:\n{script.get('body_full','')[:3000]}\n\n"
        f"Devuelve en este formato:\n\n{fmt}"
    )
    return sys_prompt, user_msg


def build_thumbnail_prompt(project, profile, script, script_type):
    """Construye el prompt para generar una miniatura cinematográfica fija.

    `script_type` es 'long' (5 min, 16:9) o 'short' (1 min, 9:16).
    """
    if script_type == "long":
        sys_prompt = CONFIG["prompts"]["thumbnail_long"]["system"]
        fmt = CONFIG["prompts"]["thumbnail_long"]["format"]
        duration_txt = "5 minutos (formato 16:9 horizontal)"
    else:
        sys_prompt = CONFIG["prompts"]["thumbnail_short"]["system"]
        fmt = CONFIG["prompts"]["thumbnail_short"]["format"]
        duration_txt = "1 minuto (formato 9:16 vertical)"

    user_msg = (
        f"Tema: {project['topic']}\n"
        f"Duración objetivo del guion: {duration_txt}\n"
        f"Título del guion: {script.get('title','')}\n"
        f"Hook: {script.get('hook','')}\n"
        f"Tipo de contenido: {profile['content_type'] if profile else 'documental'}\n"
        f"Estilo visual: {profile['style'] if profile else 'cinematográfico'}\n"
        f"Nivel de misterio: {profile['mystery_level'] if profile else 7}/10\n\n"
        f"Ángulo y tesis del guion:\n{script.get('body_full','')[:2500]}\n\n"
        f"Devuelve SIEMPRE en este formato:\n\n{fmt}"
    )
    return sys_prompt, user_msg


def call_llm(sys_prompt, user_msg):
    """Llama al LLM configurado o devuelve un placeholder para modo manual.

    Soporta:
    - manual: devuelve prompt formateado para copiar
    - openai: cualquier endpoint OpenAI-compatible (incluye MiniMax text API, LM Studio, Ollama, etc.)
    - anthropic: API de Claude (requiere SDK `anthropic`)
    - custom: un preset definido por el usuario en CONFIG["llm"]["presets"]
    """
    provider = CONFIG["llm"]["provider"]

    # Resolver configuración: si hay un preset activo, mezclarlo
    preset = None
    preset_name = CONFIG["llm"].get("active_preset")
    if preset_name and CONFIG["llm"].get("presets", {}).get(preset_name):
        preset = CONFIG["llm"]["presets"][preset_name]

    if provider == "manual":
        return "## [MODO MANUAL — Pega aquí la respuesta de tu LLM]\n\n" + (
            "### PROMPT DEL SISTEMA\n"
            f"```\n{sys_prompt}\n```\n\n"
            "### PROMPT DEL USUARIO\n"
            f"```\n{user_msg}\n```\n\n"
            "### INSTRUCCIONES\n"
            "1. Copia el prompt del sistema y del usuario\n"
            "2. Pégalo en tu LLM favorito (ChatGPT, Claude, Gemini, etc.)\n"
            "3. Pega la respuesta en el campo correspondiente abajo"
        )

    # OpenAI / OpenAI-compatible (incluye MiniMax text API si expone este formato)
    if provider in ("openai", "custom"):
        # Tomar config del preset si está activo, si no del bloque openai legacy
        if preset:
            api_key = preset.get("api_key", "")
            base_url = preset.get("base_url", "https://api.openai.com/v1")
            model = preset.get("model", "gpt-4o-mini")
        else:
            api_key = CONFIG["llm"]["openai"]["api_key"]
            base_url = CONFIG["llm"]["openai"]["base_url"]
            model = CONFIG["llm"]["openai"]["model"]
        if not api_key:
            return _manual_fallback(sys_prompt, user_msg, "No hay API key configurada")
        try:
            data = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": CONFIG["llm"]["temperature"],
                "max_tokens": CONFIG["llm"]["max_tokens"],
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url.rstrip('/')}/chat/completions",
                data=data,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = json.loads(r.read().decode("utf-8"))
                return payload["choices"][0]["message"]["content"]
        except Exception as e:
            return _manual_fallback(sys_prompt, user_msg, f"ERROR LLM ({provider}): {e}")

    # Anthropic Claude
    if provider == "anthropic":
        if preset:
            api_key = preset.get("api_key", "")
            model = preset.get("model", "claude-3-5-sonnet-20241022")
        else:
            api_key = CONFIG["llm"]["anthropic"]["api_key"]
            model = CONFIG["llm"]["anthropic"]["model"]
        if not api_key:
            return _manual_fallback(sys_prompt, user_msg, "No hay API key de Anthropic configurada")
        # Intentar usar el SDK; si no está, fallback a requests con API REST
        try:
            import anthropic  # type: ignore
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=model,
                max_tokens=CONFIG["llm"]["max_tokens"],
                system=sys_prompt,
                messages=[{"role": "user", "content": user_msg}],
            )
            return message.content[0].text
        except ImportError:
            # Fallback a la API REST directa
            try:
                data = json.dumps({
                    "model": model,
                    "max_tokens": CONFIG["llm"]["max_tokens"],
                    "system": sys_prompt,
                    "messages": [{"role": "user", "content": user_msg}],
                }).encode("utf-8")
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=data,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=120) as r:
                    payload = json.loads(r.read().decode("utf-8"))
                    return payload["content"][0]["text"]
            except Exception as e:
                return _manual_fallback(sys_prompt, user_msg, f"ERROR Anthropic: {e}")
        except Exception as e:
            return _manual_fallback(sys_prompt, user_msg, f"ERROR Anthropic: {e}")

    return _manual_fallback(sys_prompt, user_msg, f"Proveedor desconocido: {provider}")


def _manual_fallback(sys_prompt, user_msg, reason=""):
    """Devuelve un mensaje en formato manual cuando falla la API."""
    prefix = f"## [MODO MANUAL — {reason}]\n\n" if reason else "## [MODO MANUAL]\n\n"
    return prefix + (
        "### PROMPT DEL SISTEMA\n"
        f"```\n{sys_prompt}\n```\n\n"
        "### PROMPT DEL USUARIO\n"
        f"```\n{user_msg}\n```\n\n"
        "Copia y pega en tu LLM favorito, luego vuelve aquí con la respuesta."
    )


def llm_output_is_manual(text):
    """True si la respuesta es el prompt para copiar y no contenido generado."""
    return bool(text) and text.lstrip().startswith("## [MODO MANUAL")


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_research(text):
    """Parsea una respuesta de investigación en el formato estructurado."""
    sections = {
        "content": "",
        "sources": [],
        "facts": [],
        "theories": [],
        "unverified": [],
    }
    sections_map = {
        "RESUMEN": "content",
        "HECHOS CONFIRMADOS": "facts",
        "TEORÍAS Y VERSIONES": "theories",
        "TEORIAS Y VERSIONES": "theories",
        "CONTROVERSIAS Y DEBATES": "theories",
        "DATOS CLAVE": "facts",
        "FUENTES": "sources",
        "AFIRMACIONES QUE REQUIEREN VERIFICACIÓN": "unverified",
        "AFIRMACIONES QUE REQUIEREN VERIFICACION": "unverified",
    }
    cur = "content"
    buf = []

    def flush():
        nonlocal cur, buf
        if cur in ("sources", "facts", "theories", "unverified"):
            pass  # already accumulated
        else:
            if cur and buf:
                sections[cur] = (sections.get(cur) or "").strip()
                if sections[cur]:
                    sections[cur] = (sections[cur] + "\n" + "\n".join(buf).strip()).strip()
                else:
                    sections[cur] = "\n".join(buf).strip()

    for line in text.splitlines():
        s = line.strip()
        up = re.sub(r"\s+", " ", s.upper())
        matched = None
        for key, val in sections_map.items():
            if up.startswith("## " + key):
                matched = val
                break
        if matched:
            flush()
            buf = []
            cur = matched
        else:
            if cur in ("sources", "facts", "theories", "unverified"):
                if s.startswith(("-", "•", "*")):
                    sections[cur].append(s.lstrip("-•* ").strip())
                elif s:
                    sections[cur].append(s)
            else:
                buf.append(line)
    flush()
    return sections


def parse_concept(text):
    sections = {
        "angle": "",
        "thesis": "",
        "key_points": [],
        "emotional_hook": "",
        "what_they_learn": [],
        "what_they_feel": [],
        "risks": [],
    }
    sections_map = {
        "ÁNGULO": "angle",
        "ANGULO": "angle",
        "TESIS": "thesis",
        "PUNTOS CLAVE": "key_points",
        "GANCHO": "emotional_hook",
        "LO QUE EL ESPECTADOR DEBE APRENDER": "what_they_learn",
        "LO QUE EL ESPECTADOR DEBE SENTIR": "what_they_feel",
        "RIESGOS": "risks",
    }
    cur = None
    buf = []

    def flush_text():
        if cur and cur not in ("key_points", "what_they_learn", "what_they_feel", "risks"):
            sections[cur] = (sections.get(cur) or "").strip()
            if buf:
                sections[cur] = (sections[cur] + "\n" + "\n".join(buf).strip()).strip()
        elif cur in ("key_points", "what_they_learn", "what_they_feel", "risks"):
            # Already accumulated into sections[cur] in the loop
            pass

    for line in text.splitlines():
        s = line.strip()
        up = re.sub(r"\s+", " ", s.upper())
        matched = None
        for key, val in sections_map.items():
            if up.startswith("## " + key):
                matched = val
                break
        if matched:
            flush_text()
            buf = []
            cur = matched
        else:
            if cur in ("key_points", "what_they_learn", "what_they_feel", "risks"):
                m = re.match(r"^\s*\d+[\.\)]\s*(.+)", s) or re.match(r"^[-•*]\s*(.+)", s)
                if m:
                    sections[cur].append(m.group(1).strip())
                elif s:
                    sections[cur].append(s)
            elif cur:
                buf.append(line)
    flush_text()
    return sections


def parse_script(text, script_type):
    """Parsea un guion largo o corto en sus secciones."""
    out = {
        "title": "",
        "hook": "",
        "context": "",
        "development": "",
        "revelations": "",
        "conclusion": "",
        "cta": "",
        "body_full": "",
    }
    sections_map = {
        "TITULO": "title",
        "TÍTULO": "title",
        "HOOK": "hook",
        "CONTEXTO": "context",
        "DESARROLLO": "development",
        "REVELACIONES": "revelations",
        "CONCLUSION": "conclusion",
        "CONCLUSIÓN": "conclusion",
        "CTA": "cta",
        "INFORMACIÓN ESENCIAL": "context",
        "INFORMACION ESENCIAL": "context",
        "ESCALADA": "revelations",
        "REMATE": "conclusion",
    }
    cur = None
    buf = []
    for line in text.splitlines():
        s = line.strip()
        up = re.sub(r"\s+", " ", s.upper())
        matched = None
        for key, val in sections_map.items():
            if up.startswith("## " + key):
                matched = val
                break
        if matched:
            if cur:
                out[cur] = (out.get(cur) or "").strip()
            out[cur or matched] = (out.get(cur or matched, "") + "\n" + "\n".join(buf).strip()).strip()
            buf = []
            cur = matched
        else:
            buf.append(line)
    if cur:
        out[cur] = (out.get(cur, "") + "\n" + "\n".join(buf).strip()).strip()
    # body full
    parts = []
    for k in ("hook", "context", "development", "revelations", "conclusion", "cta"):
        if out.get(k):
            parts.append(out[k])
    out["body_full"] = "\n\n".join(parts).strip()
    return out


def parse_scenes_json(text):
    """Intenta extraer un JSON de una respuesta que podría tener prosa alrededor."""
    # Busca el primer [ y el último ]
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start:end + 1]
    try:
        data = json.loads(candidate)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    # Intento con bloque de código
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            return None
    return None


def parse_scenes_tst(text):
    """Parsea la salida TST Scene Director en bloques ESCENA N / TEXTO AUDIO / IMAGEN.

    Acepta líneas adicionales entre los bloques, líneas en blanco, y valores
    multilínea hasta el siguiente marcador. Devuelve lista de dicts con
    scene_number, narration_segment, image_prompt.
    """
    if not text:
        return []
    scenes = []
    current = None
    field = None
    scene_re = re.compile(r"^\s*ESCENA\s+(\d+)\s*[:.]?\s*$", re.IGNORECASE)
    field_re = re.compile(r"^\s*(TEXTO\s+AUDIO|IMAGEN)\s*:\s*(.*)$", re.IGNORECASE)

    def flush():
        if current and current.get("narration_segment") and current.get("image_prompt"):
            scenes.append(current)

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        m_scene = scene_re.match(line)
        if m_scene:
            flush()
            current = {"scene_number": int(m_scene.group(1))}
            field = None
            continue
        if current is None:
            continue
        m_field = field_re.match(line)
        if m_field:
            label = m_field.group(1).upper().replace(" ", "")
            key = "narration_segment" if label == "TEXTOAUDIO" else "image_prompt"
            current[key] = m_field.group(2).strip()
            field = key
            continue
        if field and stripped:
            current[field] = (current.get(field, "") + " " + stripped).strip()
    flush()
    return scenes


def parse_scenes(text):
    """Parsea una respuesta de escenas: intenta primero TST, luego JSON."""
    tst = parse_scenes_tst(text)
    if tst:
        return tst
    j = parse_scenes_json(text)
    if j:
        return j
    return None


def parse_prompt_json(text):
    """Intenta extraer el JSON de un prompt."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None
    return None


def parse_metadata(text, platform):
    out = {
        "titles": [],
        "description": "",
        "chapters": [],
        "tags": [],
        "hashtags": [],
        "caption": "",
        "hook": "",
        "cta": "",
        "on_screen_text": [],
    }
    cur = None
    buf = []
    for line in text.splitlines():
        s = line.strip()
        up = re.sub(r"\s+", " ", s.upper())
        if up.startswith("## TITULOS") or up.startswith("## TÍTULOS"):
            cur = "titles"
        elif up.startswith("## DESCRIPCIÓN") or up.startswith("## DESCRIPCION"):
            cur = "description"
        elif up.startswith("## CAPÍTULOS") or up.startswith("## CAPITULOS"):
            cur = "chapters"
        elif up.startswith("## TAGS"):
            cur = "tags"
        elif up.startswith("## HASHTAGS"):
            cur = "hashtags"
        elif up.startswith("## CAPTION"):
            cur = "caption"
        elif up.startswith("## HOOK"):
            cur = "hook"
        elif up.startswith("## CTA"):
            cur = "cta"
        elif up.startswith("## TEXTO EN PANTALLA"):
            cur = "on_screen_text"
        elif up.startswith("##") and cur:
            cur = None
        else:
            if cur in ("titles",):
                m = re.match(r"^\s*\d+[\.\)]\s*(.+)", s)
                if m:
                    out["titles"].append(m.group(1).strip())
            elif cur in ("tags",):
                if s and not s.startswith("#"):
                    parts = [p.strip() for p in re.split(r"[,\s]+", s) if p.strip()]
                    out["tags"].extend(parts)
            elif cur in ("hashtags",):
                for h in re.findall(r"#\w+", s):
                    out["hashtags"].append(h)
            elif cur in ("chapters",):
                if s:
                    out["chapters"].append(s)
            elif cur in ("on_screen_text",):
                m = re.match(r"^\s*\d+[\.\)]\s*(.+)", s)
                if m:
                    out["on_screen_text"].append(m.group(1).strip())
            elif cur in ("description", "caption", "hook", "cta"):
                if s:
                    out[cur] = (out[cur] + "\n" + s).strip()
    return out


def parse_thumbnail(text, script_type):
    """Extrae el bloque `## MINIATURA` de la respuesta del LLM.

    Devuelve `{"prompt": "..."}` con todo el contenido bajo `## MINIATURA`
    hasta el siguiente `##` o el fin del texto. `script_type` se ignora,
    pero se mantiene por simetría con `parse_metadata`.
    """
    out = {"prompt": ""}
    if not text:
        return out
    cur = None
    buf = []

    def flush():
        nonlocal out, cur, buf
        if cur == "miniatura" and buf:
            chunk = "\n".join(buf).strip()
            out["prompt"] = (out["prompt"] + "\n" + chunk).strip() if out["prompt"] else chunk
        buf = []

    for raw in text.splitlines():
        line = raw.rstrip()
        up = re.sub(r"\s+", " ", line.strip().upper())
        if up.startswith("## "):
            flush()
            cur = "miniatura" if up.startswith("## MINIATURA") else None
            continue
        if cur == "miniatura" and line.strip():
            buf.append(line.strip())
    flush()
    return out


# ---------------------------------------------------------------------------
# QC
# ---------------------------------------------------------------------------

def run_qc(project_id):
    """Ejecuta todos los checks y devuelve la lista de issues."""
    issues = []
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

    scenes_by_script = {}
    for sc in scenes:
        scenes_by_script.setdefault(sc["script_id"], []).append(sc)
    prompts_by_scene = {p["scene_id"]: p for p in prompts}

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
        from collections import Counter
        c = Counter(words)
        for word, n in c.most_common(10):
            if n >= cfg["repetition_threshold"]:
                issues.append(("scripts", "warning",
                    f"Palabra repetida {n}× en el guion {tlabel}: «{word}»", ttype))
                break
        # CTA
        if not s["cta"]:
            issues.append(("scripts", "warning", f"Guion {tlabel} sin CTA", "cta"))

    # Escenas (chequeo por guion, ya que cada video tiene las suyas)
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

    # Coherencia: si la investigación tiene afirmaciones sin verificar
    if research:
        unv = json.loads(research["unverified"] or "[]")
        if unv and (long_s or short_s):
            issues.append(("research", "warning",
                f"Hay {len(unv)} afirmaciones que requieren verificación en la investigación", "unverified"))

    return issues


def save_qc_issues(project_id, issues):
    with get_db() as conn:
        conn.execute("DELETE FROM qc_issues WHERE project_id=?", (project_id,))
        for stage, severity, message, field in issues:
            conn.execute("""
                INSERT INTO qc_issues (project_id, stage, severity, message, field, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (project_id, stage, severity, message, field, now_iso()))


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    with get_db() as conn:
        projects = [dict(r) for r in conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ).fetchall()]
        profiles = [dict(r) for r in conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()]
    for p in projects:
        p["stages"] = project_stage_status(p)
    return render_template("dashboard.html", projects=projects, profiles=profiles, config=CONFIG)


@app.route("/projects/new", methods=["GET", "POST"])
def new_project():
    with get_db() as conn:
        profiles = [dict(r) for r in conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()]
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        topic = request.form.get("topic", "").strip()
        profile_id = request.form.get("profile_id") or None
        if not name or not topic:
            flash("Nombre y tema son obligatorios", "error")
            return render_template("new_project.html", profiles=profiles)
        with get_db() as conn:
            cur = conn.execute("""
                INSERT INTO projects (name, topic, profile_id, status, created_at, updated_at)
                VALUES (?, ?, ?, 'research', ?, ?)
            """, (name, topic, profile_id, now_iso(), now_iso()))
            new_id = cur.lastrowid
        return redirect(url_for("view_project", project_id=new_id))
    return render_template("new_project.html", profiles=profiles, default_profile=get_default_profile())


@app.route("/projects/<int:project_id>")
def view_project(project_id):
    with get_db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            abort(404)
        project = dict(project)
        profile = get_profile(project["profile_id"])
    project["stages"] = project_stage_status(project)
    saved_prompts = list_saved_prompts(project_id)
    return render_template("project.html", project=project, profile=profile,
                           saved_prompts=saved_prompts)


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
def delete_project(project_id):
    with get_db() as conn:
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    flash("Proyecto eliminado", "ok")
    return redirect(url_for("dashboard"))


@app.route("/projects/<int:project_id>/stage-prompts/backfill", methods=["POST"])
def backfill_stage_prompts(project_id):
    """Regenera y guarda los prompts de las etapas que tengan contenido."""
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])

    generated = 0
    for stage in ("research", "concept", "script_long", "script_short",
                  "scenes", "metadata_youtube", "metadata_shorts",
                  "thumbnail_long", "thumbnail_short"):
        if _ensure_stage_prompt(project_id, stage, project, profile):
            generated += 1
    flash(f"Prompts regenerados: {generated}", "ok")
    return redirect(url_for("view_project", project_id=project_id))


# --- Investigación -----------------------------------------------------------

@app.route("/projects/<int:project_id>/research", methods=["GET", "POST"])
def research(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
    research_obj = get_or_create_research(project_id)
    saved_prompt = get_saved_prompt(project_id, "research")

    if request.method == "POST":
        action = request.form.get("action")
        if action == "generate_prompt":
            sys_p, user_p = build_research_prompt(project, profile)
            save_stage_prompt(project_id, "research", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template("research.html", project=project, profile=profile,
                                   research=research_obj, generated=generated,
                                   sys_prompt=sys_p, user_prompt=user_p,
                                   saved_prompt=True)
        elif action == "save_prompt":
            sys_p = request.form.get("sys_prompt", "").strip()
            user_p = request.form.get("user_prompt", "").strip()
            if sys_p and user_p:
                save_stage_prompt(project_id, "research", sys_p, user_p)
                flash("Prompt guardado en el proyecto", "ok")
            return redirect(url_for("research", project_id=project_id))
        elif action == "save":
            text = request.form.get("content", "").strip()
            if text:
                parsed = parse_research(text)
                with get_db() as conn:
                    conn.execute("""
                        UPDATE research SET content=?, sources=?, facts=?,
                            theories=?, unverified=?, updated_at=?
                        WHERE project_id=?
                    """, (
                        parsed["content"] or text,
                        json.dumps(parsed["sources"], ensure_ascii=False),
                        json.dumps(parsed["facts"], ensure_ascii=False),
                        json.dumps(parsed["theories"], ensure_ascii=False),
                        json.dumps(parsed["unverified"], ensure_ascii=False),
                        now_iso(), project_id,
                    ))
                    conn.execute("UPDATE projects SET updated_at=? WHERE id=?",
                                 (now_iso(), project_id))
                # Auto-guardar el prompt canónico si aún no había uno.
                _ensure_stage_prompt(project_id, "research", project, profile, None)
                flash("Investigación guardada", "ok")
            return redirect(url_for("research", project_id=project_id))

    sources = json.loads(research_obj.get("sources") or "[]")
    facts = json.loads(research_obj.get("facts") or "[]")
    return render_template("research.html", project=project, profile=profile,
                           research=research_obj, sources=sources, facts=facts,
                           saved_prompt=saved_prompt)


# --- Concepto ----------------------------------------------------------------

@app.route("/projects/<int:project_id>/concept", methods=["GET", "POST"])
def concept(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        research_obj = fetch_optional_dict(conn, "SELECT * FROM research WHERE project_id=?", (project_id,))
    concept_obj = get_or_create_concept(project_id)
    saved_prompt = get_saved_prompt(project_id, "concept")

    if request.method == "POST":
        action = request.form.get("action")
        if action == "generate_prompt":
            if not research_obj or not research_obj.get("content"):
                flash("Necesitas tener investigación antes de generar el concepto", "error")
                return redirect(url_for("research", project_id=project_id))
            sys_p, user_p = build_concept_prompt(project, profile, research_obj)
            save_stage_prompt(project_id, "concept", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template("concept.html", project=project, profile=profile,
                                   concept=concept_obj, generated=generated,
                                   sys_prompt=sys_p, user_prompt=user_p,
                                   saved_prompt=True)
        elif action == "save_prompt":
            sys_p = request.form.get("sys_prompt", "").strip()
            user_p = request.form.get("user_prompt", "").strip()
            if sys_p and user_p:
                save_stage_prompt(project_id, "concept", sys_p, user_p)
                flash("Prompt guardado en el proyecto", "ok")
            return redirect(url_for("concept", project_id=project_id))
        elif action == "save":
            text = request.form.get("text", "").strip()
            if text:
                parsed = parse_concept(text)
                with get_db() as conn:
                    conn.execute("""
                        UPDATE concept SET angle=?, thesis=?, key_points=?,
                            emotional_hook=?, what_they_learn=?, what_they_feel=?,
                            risks=?, updated_at=? WHERE project_id=?
                    """, (
                        parsed["angle"], parsed["thesis"],
                        json.dumps(parsed["key_points"], ensure_ascii=False),
                        parsed["emotional_hook"],
                        json.dumps(parsed["what_they_learn"], ensure_ascii=False),
                        json.dumps(parsed["what_they_feel"], ensure_ascii=False),
                        json.dumps(parsed["risks"], ensure_ascii=False),
                        now_iso(), project_id,
                    ))
                    conn.execute("UPDATE projects SET status='concept', updated_at=? WHERE id=?",
                                 (now_iso(), project_id))
                _ensure_stage_prompt(project_id, "concept", project, profile,
                                     {"research": research_obj})
                flash("Concepto guardado", "ok")
            return redirect(url_for("concept", project_id=project_id))

    key_points = json.loads(concept_obj.get("key_points") or "[]")
    return render_template("concept.html", project=project, profile=profile,
                           concept=concept_obj, key_points=key_points,
                           saved_prompt=saved_prompt)


# --- Guiones -----------------------------------------------------------------

@app.route("/projects/<int:project_id>/scripts", methods=["GET", "POST"])
def scripts(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        research_obj = fetch_optional_dict(conn, "SELECT * FROM research WHERE project_id=?", (project_id,))
        concept_obj = fetch_optional_dict(conn, "SELECT * FROM concept WHERE project_id=?", (project_id,))
        long_s = get_script(project_id, "long")
        short_s = get_script(project_id, "short")
    saved_long = get_saved_prompt(project_id, "script_long")
    saved_short = get_saved_prompt(project_id, "script_short")

    if request.method == "POST":
        action = request.form.get("action")
        stype = request.form.get("script_type")
        if action == "generate_prompt" and stype in ("long", "short"):
            if not concept_obj or not concept_obj.get("angle"):
                flash("Necesitas un concepto antes de generar el guion", "error")
                return redirect(url_for("concept", project_id=project_id))
            sys_p, user_p = build_script_prompt(project, profile, research_obj, concept_obj, stype)
            save_stage_prompt(project_id, f"script_{stype}", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template("scripts.html", project=project, profile=profile,
                                   long_s=long_s, short_s=short_s,
                                   generated=generated, gen_type=stype,
                                   sys_prompt=sys_p, user_prompt=user_p,
                                   saved_long=saved_long, saved_short=saved_short)
        elif action == "save_prompt" and stype in ("long", "short"):
            sys_p = request.form.get("sys_prompt", "").strip()
            user_p = request.form.get("user_prompt", "").strip()
            if sys_p and user_p:
                save_stage_prompt(project_id, f"script_{stype}", sys_p, user_p)
                flash(f"Prompt de guion {stype} guardado en el proyecto", "ok")
            return redirect(url_for("scripts", project_id=project_id))
        elif action == "save" and stype in ("long", "short"):
            text = request.form.get("text", "").strip()
            if text:
                parsed = parse_script(text, stype)
                wc = count_words(parsed["body_full"] or text)
                with get_db() as conn:
                    existing = conn.execute(
                        "SELECT id FROM scripts WHERE project_id=? AND type=?",
                        (project_id, stype)
                    ).fetchone()
                    if existing:
                        conn.execute("""
                            UPDATE scripts SET title=?, hook=?, context=?, development=?,
                                revelations=?, conclusion=?, cta=?, body_full=?,
                                word_count=?, updated_at=? WHERE id=?
                        """, (
                            parsed["title"], parsed["hook"], parsed["context"],
                            parsed["development"], parsed["revelations"],
                            parsed["conclusion"], parsed["cta"],
                            parsed["body_full"], wc, now_iso(), existing["id"],
                        ))
                    else:
                        conn.execute("""
                            INSERT INTO scripts (project_id, type, title, hook, context,
                                development, revelations, conclusion, cta, body_full,
                                word_count, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            project_id, stype, parsed["title"], parsed["hook"],
                            parsed["context"], parsed["development"],
                            parsed["revelations"], parsed["conclusion"],
                            parsed["cta"], parsed["body_full"], wc, now_iso(),
                        ))
                    conn.execute("UPDATE projects SET status='scripts', updated_at=? WHERE id=?",
                                 (now_iso(), project_id))
                _ensure_stage_prompt(
                    project_id, f"script_{stype}", project, profile,
                    {"research": research_obj, "concept": concept_obj},
                )
                flash(f"Guion {stype} guardado", "ok")
            return redirect(url_for("scripts", project_id=project_id))

    return render_template("scripts.html", project=project, profile=profile,
                           long_s=long_s, short_s=short_s,
                           saved_long=saved_long, saved_short=saved_short)


# --- Escenas -----------------------------------------------------------------

@app.route("/projects/<int:project_id>/scenes", methods=["GET", "POST"])
def scenes(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        scripts_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM scripts WHERE project_id=?", (project_id,)
        ).fetchall()]

    def default_script_id():
        long_s = next((s for s in scripts_rows if s["type"] == "long"), None)
        return long_s["id"] if long_s else (scripts_rows[0]["id"] if scripts_rows else None)

    def fetch_scenes_for(sid):
        if sid is None:
            return []
        with get_db() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM scenes WHERE project_id=? AND script_id=? ORDER BY scene_number",
                (project_id, sid),
            ).fetchall()]

    raw_script_id = request.values.get("script_id")
    if raw_script_id and any(str(s["id"]) == str(raw_script_id) for s in scripts_rows):
        active_script_id = int(raw_script_id)
    else:
        active_script_id = default_script_id()
    scenes_rows = fetch_scenes_for(active_script_id)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "generate_prompt":
            script_id = request.form.get("script_id") or active_script_id
            script = next((s for s in scripts_rows if str(s["id"]) == str(script_id)), None)
            if not script:
                flash("Selecciona un guion", "error")
                return redirect(url_for("scenes", project_id=project_id))
            sys_p, user_p = build_scenes_prompt(project, profile, script)
            save_stage_prompt(project_id, "scenes", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template("scenes.html", project=project, profile=profile,
                                   scripts=scripts_rows, scenes=scenes_rows,
                                   generated=generated, gen_script_id=script_id,
                                   sys_prompt=sys_p, user_prompt=user_p,
                                   saved_prompt=True,
                                   active_script_id=script_id)
        elif action == "save_prompt":
            sys_p = request.form.get("sys_prompt", "").strip()
            user_p = request.form.get("user_prompt", "").strip()
            if sys_p and user_p:
                save_stage_prompt(project_id, "scenes", sys_p, user_p)
                flash("Prompt de escenas guardado en el proyecto", "ok")
            return redirect(url_for("scenes", project_id=project_id, script_id=active_script_id))
        elif action == "save":
            text = request.form.get("text", "").strip()
            script_id = request.form.get("script_id") or active_script_id
            if text and script_id:
                parsed = parse_scenes(text)
                if not parsed:
                    flash("No se pudo extraer escenas de la respuesta (¿formato TST correcto?)", "error")
                    return redirect(url_for("scenes", project_id=project_id, script_id=script_id))
                # Estimar duración por escena si el LLM no la incluyó.
                wpm = (profile.get("narration_speed") if profile else None) or 150
                total_words = sum(count_words(sc.get("narration_segment", "")) for sc in parsed)
                for sc in parsed:
                    if not sc.get("duration_seconds") and total_words > 0:
                        w = count_words(sc.get("narration_segment", ""))
                        sc["duration_seconds"] = max(1, round(w / wpm * 60))
                with get_db() as conn:
                    conn.execute("DELETE FROM scenes WHERE project_id=? AND script_id=?",
                                 (project_id, script_id))
                    for sc in parsed:
                        try:
                            scene_num = int(sc.get("scene_number", 0))
                        except Exception:
                            scene_num = 0
                        try:
                            dur = int(sc.get("duration_seconds", 0))
                        except Exception:
                            dur = 0
                        image_prompt = (
                            sc.get("image_prompt")
                            or sc.get("visual_description")
                            or ""
                        )
                        conn.execute("""
                            INSERT INTO scenes (project_id, script_id, scene_number,
                                narration, visual_description, camera_movement,
                                transition, duration_seconds, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            project_id, script_id, scene_num,
                            sc.get("narration_segment", ""),
                            image_prompt,
                            sc.get("camera_movement", "") or "",
                            sc.get("transition", "") or "",
                            dur, now_iso(),
                        ))
                    conn.execute("UPDATE projects SET status='scenes', updated_at=? WHERE id=?",
                                  (now_iso(), project_id))
                # Auto-guardar prompt de escenas usando el guion largo como referencia
                long_script = get_script(project_id, "long") or get_script(project_id, "short")
                if long_script:
                    _ensure_stage_prompt(
                        project_id, "scenes", project, profile,
                        {"script": long_script},
                    )
                flash(f"Guardadas {len(parsed)} escenas del guion seleccionado", "ok")
            return redirect(url_for("scenes", project_id=project_id, script_id=script_id))
        elif action == "delete":
            scene_id = request.form.get("scene_id")
            with get_db() as conn:
                conn.execute("DELETE FROM scenes WHERE id=?", (scene_id,))
            return redirect(url_for("scenes", project_id=project_id, script_id=active_script_id))

    saved_prompt = get_saved_prompt(project_id, "scenes")
    return render_template("scenes.html", project=project, profile=profile,
                           scripts=scripts_rows, scenes=scenes_rows,
                           saved_prompt=saved_prompt,
                           active_script_id=active_script_id)


# --- Prompts -----------------------------------------------------------------

# --- Metadata ----------------------------------------------------------------

@app.route("/projects/<int:project_id>/metadata", methods=["GET", "POST"])
def metadata(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        scripts_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM scripts WHERE project_id=?", (project_id,)
        ).fetchall()]
        meta_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM metadata_records WHERE project_id=?", (project_id,)
        ).fetchall()]

    meta_by_platform = {m["platform"]: m for m in meta_rows}

    if request.method == "POST":
        action = request.form.get("action")
        platform = request.form.get("platform")
        if action == "generate_prompt" and platform in ("youtube", "shorts"):
            script_id = request.form.get("script_id")
            script = next((s for s in scripts_rows if str(s["id"]) == str(script_id)), None)
            if not script:
                flash("Selecciona un guion", "error")
                return redirect(url_for("metadata", project_id=project_id))
            sys_p, user_p = build_metadata_prompt(project, profile, script, platform)
            save_stage_prompt(project_id, f"metadata_{platform}", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            saved_yt = get_saved_prompt(project_id, "metadata_youtube")
            saved_sh = get_saved_prompt(project_id, "metadata_shorts")
            return render_template("metadata.html", project=project, profile=profile,
                                   scripts=scripts_rows, meta_by_platform=meta_by_platform,
                                   generated=generated, gen_platform=platform,
                                   gen_script_id=script_id,
                                   sys_prompt=sys_p, user_prompt=user_p,
                                   saved_yt=saved_yt, saved_sh=saved_sh)
        elif action == "save_prompt" and platform in ("youtube", "shorts"):
            sys_p = request.form.get("sys_prompt", "").strip()
            user_p = request.form.get("user_prompt", "").strip()
            if sys_p and user_p:
                save_stage_prompt(project_id, f"metadata_{platform}", sys_p, user_p)
                flash(f"Prompt de metadata {platform} guardado en el proyecto", "ok")
            return redirect(url_for("metadata", project_id=project_id))
        elif action == "save" and platform in ("youtube", "shorts"):
            text = request.form.get("text", "").strip()
            if text:
                parsed = parse_metadata(text, platform)
                with get_db() as conn:
                    existing = conn.execute(
                        "SELECT id FROM metadata_records WHERE project_id=? AND platform=?",
                        (project_id, platform)
                    ).fetchone()
                    fields = (
                        json.dumps(parsed["titles"], ensure_ascii=False),
                        parsed["description"],
                        json.dumps(parsed["chapters"], ensure_ascii=False),
                        json.dumps(parsed["tags"], ensure_ascii=False),
                        json.dumps(parsed["hashtags"], ensure_ascii=False),
                        parsed["caption"], parsed["hook"], parsed["cta"],
                        json.dumps(parsed["on_screen_text"], ensure_ascii=False),
                    )
                    if existing:
                        conn.execute("""
                            UPDATE metadata_records SET titles=?, description=?,
                                chapters=?, tags=?, hashtags=?, caption=?, hook=?, cta=?,
                                on_screen_text=?, updated_at=? WHERE id=?
                        """, (*fields, now_iso(), existing["id"]))
                    else:
                        conn.execute("""
                            INSERT INTO metadata_records (project_id, platform, titles,
                                description, chapters, tags, hashtags, caption, hook,
                                cta, on_screen_text, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (project_id, platform, *fields, now_iso()))
                    conn.execute("UPDATE projects SET status='metadata', updated_at=? WHERE id=?",
                                 (now_iso(), project_id))
                # Resolver script (para el prompt): preferir el enviado en el form,
                # si no, usar el guion largo o corto del proyecto.
                script = None
                sid = request.form.get("script_id")
                if sid:
                    script = next((s for s in scripts_rows if str(s["id"]) == str(sid)), None)
                if not script:
                    script = get_script(project_id, "long") or get_script(project_id, "short")
                _ensure_stage_prompt(
                    project_id, f"metadata_{platform}", project, profile,
                    {"script": script or {}},
                )
                flash(f"Metadata {platform} guardada", "ok")
            return redirect(url_for("metadata", project_id=project_id))

    for m in meta_by_platform.values():
        m["titles_list"] = json.loads(m.get("titles") or "[]")
        m["chapters_list"] = json.loads(m.get("chapters") or "[]")
        m["tags_list"] = json.loads(m.get("tags") or "[]")
        m["hashtags_list"] = json.loads(m.get("hashtags") or "[]")
        m["on_screen_list"] = json.loads(m.get("on_screen_text") or "[]")
    saved_yt = get_saved_prompt(project_id, "metadata_youtube")
    saved_sh = get_saved_prompt(project_id, "metadata_shorts")
    return render_template("metadata.html", project=project, profile=profile,
                           scripts=scripts_rows, meta_by_platform=meta_by_platform,
                           saved_yt=saved_yt, saved_sh=saved_sh)


# --- Miniaturas --------------------------------------------------------------

@app.route("/projects/<int:project_id>/thumbnails", methods=["GET", "POST"])
def thumbnails(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        scripts_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM scripts WHERE project_id=?", (project_id,)
        ).fetchall()]
        thumb_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM thumbnail_records WHERE project_id=?", (project_id,)
        ).fetchall()]

    thumb_by_type = {t["script_type"]: t for t in thumb_rows}
    saved_long = get_saved_prompt(project_id, "thumbnail_long")
    saved_short = get_saved_prompt(project_id, "thumbnail_short")

    if request.method == "POST":
        action = request.form.get("action")
        script_type = request.form.get("script_type")
        if script_type not in ("long", "short"):
            flash("Tipo de miniatura no válido", "error")
            return redirect(url_for("thumbnails", project_id=project_id))

        if action == "generate_prompt":
            script_id = request.form.get("script_id")
            script = next(
                (s for s in scripts_rows if str(s["id"]) == str(script_id)), None,
            )
            if not script:
                flash("Selecciona un guion", "error")
                return redirect(url_for("thumbnails", project_id=project_id))
            sys_p, user_p = build_thumbnail_prompt(project, profile, script, script_type)
            save_stage_prompt(project_id, f"thumbnail_{script_type}", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template("thumbnails.html", project=project, profile=profile,
                                   scripts=scripts_rows,
                                   thumb_by_type=thumb_by_type,
                                   generated=generated, gen_type=script_type,
                                   gen_script_id=script_id,
                                   sys_prompt=sys_p, user_prompt=user_p,
                                   saved_long=saved_long, saved_short=saved_short)
        elif action == "save_prompt":
            sys_p = request.form.get("sys_prompt", "").strip()
            user_p = request.form.get("user_prompt", "").strip()
            if sys_p and user_p:
                save_stage_prompt(project_id, f"thumbnail_{script_type}", sys_p, user_p)
                flash(f"Prompt de miniatura {script_type} guardado", "ok")
            return redirect(url_for("thumbnails", project_id=project_id))
        elif action == "save":
            text = request.form.get("text", "").strip()
            if text:
                parsed = parse_thumbnail(text, script_type)
                prompt_text = parsed["prompt"].strip()
                if not prompt_text:
                    flash("No se pudo extraer la miniatura (¿formato correcto?)", "error")
                    return redirect(url_for("thumbnails", project_id=project_id))
                with get_db() as conn:
                    existing = conn.execute(
                        "SELECT id FROM thumbnail_records "
                        "WHERE project_id=? AND script_type=?",
                        (project_id, script_type),
                    ).fetchone()
                    if existing:
                        conn.execute("""
                            UPDATE thumbnail_records SET prompt=?, updated_at=?
                            WHERE id=?
                        """, (prompt_text, now_iso(), existing["id"]))
                    else:
                        conn.execute("""
                            INSERT INTO thumbnail_records
                            (project_id, script_type, prompt, updated_at)
                            VALUES (?, ?, ?, ?)
                        """, (project_id, script_type, prompt_text, now_iso()))
                    conn.execute(
                        "UPDATE projects SET status='thumbnails', updated_at=? WHERE id=?",
                        (now_iso(), project_id),
                    )
                # Auto-guardar el prompt canónico de la etapa.
                script = next(
                    (s for s in scripts_rows if s["type"] == script_type), None,
                )
                if script:
                    _ensure_stage_prompt(
                        project_id, f"thumbnail_{script_type}", project, profile,
                        {"script": script},
                    )
                flash(f"Miniatura {script_type} guardada", "ok")
            return redirect(url_for("thumbnails", project_id=project_id))

    return render_template("thumbnails.html", project=project, profile=profile,
                           scripts=scripts_rows, thumb_by_type=thumb_by_type,
                           saved_long=saved_long, saved_short=saved_short)


# --- QC ----------------------------------------------------------------------

@app.route("/projects/<int:project_id>/qc", methods=["GET", "POST"])
def qc(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
    if request.method == "POST":
        action = request.form.get("action", "analyze")
        if action == "skip":
            with get_db() as conn:
                conn.execute("DELETE FROM qc_issues WHERE project_id=?", (project_id,))
                conn.execute("UPDATE projects SET status='ready', updated_at=? WHERE id=?",
                             (now_iso(), project_id))
            flash("Análisis omitido: el proyecto se ha marcado como listo para exportar", "ok")
            return redirect(url_for("qc", project_id=project_id, skipped=1))
        issues = run_qc(project_id)
        save_qc_issues(project_id, issues)
        errors = [i for i in issues if i[1] == "error"]
        with get_db() as conn:
            if errors:
                conn.execute("UPDATE projects SET updated_at=? WHERE id=?",
                             (now_iso(), project_id))
            else:
                conn.execute("UPDATE projects SET status='ready', updated_at=? WHERE id=?",
                             (now_iso(), project_id))
        flash(f"Análisis completado: {len(issues)} avisos", "ok")
        if not issues:
            return redirect(url_for("qc", project_id=project_id, clean=1))
        return redirect(url_for("qc", project_id=project_id))
    with get_db() as conn:
        issues = [dict(r) for r in conn.execute(
            """SELECT * FROM qc_issues WHERE project_id=?
               ORDER BY CASE severity
                            WHEN 'error' THEN 0
                            WHEN 'warning' THEN 1
                            ELSE 2
                        END, stage""",
            (project_id,)
        ).fetchall()]
        last_run_row = conn.execute(
            "SELECT MAX(created_at) AS last FROM qc_issues WHERE project_id=?",
            (project_id,),
        ).fetchone()
        last_run = last_run_row["last"] if last_run_row else None
    return render_template("qc.html", project=project, issues=issues,
                           last_run=last_run)


# --- Export ------------------------------------------------------------------

@app.route("/projects/<int:project_id>/export", methods=["GET", "POST"])
def export(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        research_obj = fetch_optional_dict(conn, "SELECT * FROM research WHERE project_id=?", (project_id,))
        concept_obj = fetch_optional_dict(conn, "SELECT * FROM concept WHERE project_id=?", (project_id,))
        scripts_rows = [dict(r) for r in conn.execute("SELECT * FROM scripts WHERE project_id=?", (project_id,)).fetchall()]
        scenes_rows = [dict(r) for r in conn.execute("SELECT * FROM scenes WHERE project_id=? ORDER BY scene_number", (project_id,)).fetchall()]
        meta_rows = [dict(r) for r in conn.execute("SELECT * FROM metadata_records WHERE project_id=?", (project_id,)).fetchall()]
        thumb_rows = [dict(r) for r in conn.execute("SELECT * FROM thumbnail_records WHERE project_id=?", (project_id,)).fetchall()]

    if request.method == "POST":
        # Construir paquete
        safe_name = re.sub(r"[^\w\-]+", "_", project["name"]).strip("_") or f"proyecto_{project_id}"
        out_dir = PROJECTS_DIR / f"{safe_name}_{project_id}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)

        # 00_resumen.md
        with open(out_dir / "00_RESUMEN.md", "w", encoding="utf-8") as f:
            f.write(f"# {project['name']}\n\n")
            f.write(f"**Tema:** {project['topic']}\n\n")
            f.write(f"**Estado:** {project['status']}\n\n")
            f.write(f"**Creado:** {project['created_at']}\n\n")
            if profile:
                f.write(f"**Perfil:** {profile['name']}\n\n")
                f.write(f"- Tipo: {profile.get('content_type','')}\n")
                f.write(f"- Tono: {profile.get('tone','')}\n")
                f.write(f"- Estilo: {profile.get('style','')}\n")
                f.write(f"- Misterio: {profile.get('mystery_level','')}/10\n")
                f.write(f"- Dramatización: {profile.get('drama_level','')}/10\n")
                f.write(f"- Velocidad: {profile.get('narration_speed','')} ppm\n")

        # 01_investigacion.md
        if research_obj:
            with open(out_dir / "01_investigacion.md", "w", encoding="utf-8") as f:
                f.write(f"# Investigación — {project['name']}\n\n")
                f.write((research_obj.get("content") or "") + "\n\n")
                sources = json.loads(research_obj.get("sources") or "[]")
                if sources:
                    f.write("## Fuentes\n\n")
                    for s in sources:
                        f.write(f"- {s}\n")

        # 02_concepto.md
        if concept_obj and concept_obj.get("angle"):
            with open(out_dir / "02_concepto.md", "w", encoding="utf-8") as f:
                f.write(f"# Concepto — {project['name']}\n\n")
                f.write(f"## Ángulo\n\n{concept_obj.get('angle','')}\n\n")
                f.write(f"## Tesis\n\n{concept_obj.get('thesis','')}\n\n")
                kp = json.loads(concept_obj.get("key_points") or "[]")
                if kp:
                    f.write("## Puntos clave\n\n")
                    for i, p in enumerate(kp, 1):
                        f.write(f"{i}. {p}\n")
                    f.write("\n")
                if concept_obj.get("emotional_hook"):
                    f.write(f"## Gancho emocional\n\n{concept_obj['emotional_hook']}\n\n")
                wl = json.loads(concept_obj.get("what_they_learn") or "[]")
                if wl:
                    f.write("## Qué aprenden\n\n")
                    for p in wl:
                        f.write(f"- {p}\n")
                    f.write("\n")
                wf = json.loads(concept_obj.get("what_they_feel") or "[]")
                if wf:
                    f.write("## Qué sienten\n\n")
                    for p in wf:
                        f.write(f"- {p}\n")
                    f.write("\n")
                rk = json.loads(concept_obj.get("risks") or "[]")
                if rk:
                    f.write("## Riesgos\n\n")
                    for p in rk:
                        f.write(f"- {p}\n")

        # 03_guiones/
        if scripts_rows:
            gdir = out_dir / "03_guiones"
            gdir.mkdir(exist_ok=True)
            for s in scripts_rows:
                fname = f"guion_{s['type']}.md"
                with open(gdir / fname, "w", encoding="utf-8") as f:
                    f.write(f"# {s.get('title','')}\n\n")
                    f.write(f"**Tipo:** {s['type']} ({s.get('word_count',0)} palabras)\n\n")
                    if s.get("hook"):
                        f.write(f"## Hook\n\n{s['hook']}\n\n")
                    if s.get("context"):
                        f.write(f"## Contexto\n\n{s['context']}\n\n")
                    if s.get("development"):
                        f.write(f"## Desarrollo\n\n{s['development']}\n\n")
                    if s.get("revelations"):
                        f.write(f"## Revelaciones\n\n{s['revelations']}\n\n")
                    if s.get("conclusion"):
                        f.write(f"## Conclusión\n\n{s['conclusion']}\n\n")
                    if s.get("cta"):
                        f.write(f"## CTA\n\n{s['cta']}\n\n")

        # 04_escenas/
        # Formato obligatorio: un único .md con todas las escenas, sin
        # líneas en blanco entre filas (formato compacto).
        #   ## ESCENA N
        #   **TEXTO AUDIO:** [narración exacta]
        #   **IMAGEN:** [prompt cinematográfico]
        if scenes_rows:
            edir = out_dir / "04_escenas"
            edir.mkdir(exist_ok=True)
            with open(edir / "escenas.md", "w", encoding="utf-8") as f:
                f.write(f"# Escenas — {project['name']}\n")
                f.write(f"_Total: {len(scenes_rows)} escenas · "
                        f"duración acumulada: "
                        f"{sum(s.get('duration_seconds', 0) for s in scenes_rows)}s_\n")
                f.write("---\n")
                for s in scenes_rows:
                    imagen = s.get("visual_description", "").strip()
                    f.write(f"## ESCENA {s['scene_number']}\n")
                    f.write(f"**TEXTO AUDIO:** {s.get('narration','').strip()}\n")
                    f.write(f"**IMAGEN:** {imagen}\n")
                    f.write(f"_Cámara: {s.get('camera_movement','')} · "
                            f"Transición: {s.get('transition','')} · "
                            f"Duración: {s.get('duration_seconds',0)}s_\n")
                    f.write("---\n")

        # 05_metadata/
        if meta_rows:
            mdir = out_dir / "05_metadata"
            mdir.mkdir(exist_ok=True)
            for m in meta_rows:
                fname = f"metadata_{m['platform']}.md"
                with open(mdir / fname, "w", encoding="utf-8") as f:
                    f.write(f"# Metadata — {m['platform']}\n\n")
                    titles = json.loads(m.get("titles") or "[]")
                    if titles:
                        f.write("## Títulos\n\n")
                        for i, t in enumerate(titles, 1):
                            f.write(f"{i}. {t}\n")
                        f.write("\n")
                    if m.get("description"):
                        f.write(f"## Descripción\n\n{m['description']}\n\n")
                    chapters = json.loads(m.get("chapters") or "[]")
                    if chapters:
                        f.write("## Capítulos\n\n")
                        for c in chapters:
                            f.write(f"{c}\n")
                        f.write("\n")
                    tags = json.loads(m.get("tags") or "[]")
                    if tags:
                        f.write(f"## Tags\n\n{', '.join(tags)}\n\n")
                    hashtags = json.loads(m.get("hashtags") or "[]")
                    if hashtags:
                        f.write(f"## Hashtags\n\n{' '.join(hashtags)}\n\n")
                    if m.get("caption"):
                        f.write(f"## Caption\n\n{m['caption']}\n\n")
                    if m.get("hook"):
                        f.write(f"## Hook\n\n{m['hook']}\n\n")
                    if m.get("cta"):
                        f.write(f"## CTA\n\n{m['cta']}\n\n")
                    ost = json.loads(m.get("on_screen_text") or "[]")
                    if ost:
                        f.write("## Texto en pantalla\n\n")
                        for i, t in enumerate(ost, 1):
                            f.write(f"{i}. {t}\n")

        # 06_thumbnails/
        if thumb_rows:
            tdir = out_dir / "06_thumbnails"
            tdir.mkdir(exist_ok=True)
            for t in thumb_rows:
                stype = t["script_type"]
                aspect = "16:9 (horizontal)" if stype == "long" else "9:16 (vertical)"
                fname = f"thumbnail_{stype}.md"
                with open(tdir / fname, "w", encoding="utf-8") as f:
                    f.write(f"# Miniatura — guion {stype} ({aspect})\n\n")
                    f.write(f"_Actualizado: {t['updated_at']}_\n\n")
                    f.write("```\n")
                    f.write((t.get("prompt") or "").strip())
                    f.write("\n```\n")

        # 07_prompts_usados.md
        stage_prompts = list_saved_prompts(project_id)
        if stage_prompts:
            stage_labels = {
                "research": "Investigación",
                "concept": "Concepto",
                "script_long": "Guion 5 min",
                "script_short": "Guion 1 min",
                "scenes": "Escenas",
                "metadata_youtube": "Metadata YouTube",
                "metadata_shorts": "Metadata Shorts",
                "thumbnail_long": "Miniatura 5 min",
                "thumbnail_short": "Miniatura 1 min",
            }
            with open(out_dir / "07_prompts_usados.md", "w", encoding="utf-8") as f:
                f.write(f"# Prompts usados en {project['name']}\n\n")
                f.write("Estos son los prompts que se generaron y editaron durante el proyecto. Sirven como referencia y para reproducir el contenido.\n\n")
                for stage, p in stage_prompts.items():
                    label = stage_labels.get(stage, stage)
                    f.write(f"## {label}\n\n")
                    f.write(f"_Actualizado: {p['updated_at']}_\n\n")
                    f.write("### Prompt del sistema\n\n```\n")
                    f.write(p.get("sys_prompt", ""))
                    f.write("\n```\n\n### Prompt del usuario\n\n```\n")
                    f.write(p.get("user_prompt", ""))
                    f.write("\n```\n\n---\n\n")

        # 08_paquete_completo.json
        bundle = {
            "project": project,
            "profile": profile,
            "research": research_obj,
            "concept": concept_obj,
            "scripts": scripts_rows,
            "scenes": scenes_rows,
            "metadata": meta_rows,
            "thumbnails": thumb_rows,
            "stage_prompts": stage_prompts,
            "exported_at": now_iso(),
        }
        with open(out_dir / "08_paquete_completo.json", "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)

        # Crear ZIP
        zip_path = PROJECTS_DIR / f"{safe_name}_{project_id}.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(out_dir):
                for file in files:
                    full = Path(root) / file
                    arc = full.relative_to(out_dir.parent)
                    zf.write(full, arc)
        flash(f"Proyecto exportado en {zip_path.name}", "ok")
        return send_file(zip_path, as_attachment=True,
                         download_name=zip_path.name)

    with get_db() as conn:
        qc_errors = conn.execute(
            "SELECT COUNT(*) AS n FROM qc_issues WHERE project_id=? AND severity='error'",
            (project_id,),
        ).fetchone()["n"]

    return render_template("export.html", project=project, profile=profile,
                           has_research=bool(research_obj.get("content")),
                           has_concept=bool(concept_obj.get("angle")),
                           scripts=scripts_rows,
                           scenes=scenes_rows,
                           metadata=meta_rows,
                           thumbnails=thumb_rows,
                           qc_errors=qc_errors)


# --- Perfiles ----------------------------------------------------------------

@app.route("/profiles", methods=["GET", "POST"])
def profiles():
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
        elif action == "delete":
            pid = request.form.get("profile_id")
            with get_db() as conn:
                conn.execute("DELETE FROM profiles WHERE id=?", (pid,))
        return redirect(url_for("profiles"))
    with get_db() as conn:
        profiles_list = [dict(r) for r in conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()]
    for p in profiles_list:
        try:
            p["platforms_list"] = json.loads(p.get("platforms") or "[]")
        except Exception:
            p["platforms_list"] = []
    return render_template("profiles.html", profiles=profiles_list, config=CONFIG)


# --- Settings ----------------------------------------------------------------

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        action = request.form.get("action", "save")

        if action == "save_preset" and request.form.get("preset_key"):
            key = request.form.get("preset_key").strip()
            if not key:
                flash("Nombre del preset vacío", "error")
                return redirect(url_for("settings"))
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
                # También forzar provider al tipo del preset
                preset_type = CONFIG["llm"]["presets"][key].get("type", "openai")
                if preset_type == "anthropic":
                    CONFIG["llm"]["provider"] = "anthropic"
                else:
                    CONFIG["llm"]["provider"] = "openai"
                flash(f"Preset «{key}» activado. El provider se ha ajustado.", "ok")
            else:
                flash("Preset no encontrado", "error")

        else:
            # Guardar config global
            CONFIG["llm"]["provider"] = request.form.get("provider", "manual")
            CONFIG["llm"]["openai"]["api_key"] = request.form.get("openai_key", "").strip()
            CONFIG["llm"]["openai"]["model"] = request.form.get("openai_model", "gpt-4o-mini").strip()
            CONFIG["llm"]["openai"]["base_url"] = request.form.get("openai_base", "https://api.openai.com/v1").strip()
            CONFIG["llm"]["anthropic"]["api_key"] = request.form.get("anthropic_key", "").strip()
            CONFIG["llm"]["anthropic"]["model"] = request.form.get("anthropic_model", "claude-3-5-sonnet-20241022").strip()
            flash("Configuración guardada", "ok")

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f, ensure_ascii=False, indent=2)
        return redirect(url_for("settings"))

    # Filtrar presets reales (sin _comment)
    presets = {k: v for k, v in CONFIG["llm"].get("presets", {}).items() if not k.startswith("_")}
    return render_template("settings.html", config=CONFIG, presets=presets)


# ---------------------------------------------------------------------------
# Contexto de plantilla
# ---------------------------------------------------------------------------

PROVIDER_NAMES = {
    "manual": "Modo manual",
    "openai": "OpenAI-compatible",
    "anthropic": "Anthropic Claude",
    "custom": "Preset personalizado",
}


def llm_mode():
    """Cómo se generará el contenido: a mano o contra una API."""
    provider = CONFIG["llm"].get("provider", "manual")
    if provider == "manual":
        return {"key": "manual", "label": PROVIDER_NAMES["manual"],
                "detail": "copias los prompts a tu LLM", "target": "tu LLM"}
    if provider == "custom":
        preset_key = CONFIG["llm"].get("active_preset") or ""
        preset = CONFIG["llm"].get("presets", {}).get(preset_key, {})
        model = preset.get("model", "")
        return {"key": "api", "label": preset.get("label") or preset_key or "Preset",
                "detail": model, "target": model or preset.get("label") or "la API"}
    model = CONFIG["llm"].get(provider, {}).get("model", "")
    return {"key": "api", "label": PROVIDER_NAMES.get(provider, provider),
            "detail": model, "target": model or PROVIDER_NAMES.get(provider, provider)}


@app.context_processor
def inject_globals():
    return {
        "app_name": CONFIG["app"]["name"],
        "app_tagline": CONFIG["app"]["tagline"],
        "app_version": CONFIG["app"]["version"],
        "pipeline": pipeline_view,
        "status_label": status_label,
        "timecode": format_timecode,
        "llm": llm_mode(),
        "provider_names": PROVIDER_NAMES,
        "is_manual_output": llm_output_is_manual,
        "qc_checks": CONFIG["qc"]["checks"],
    }


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import sys
    print("=" * 60)
    print(f"  {CONFIG['app']['name']} — {CONFIG['app']['tagline']}")
    print(f"  v{CONFIG['app']['version']}")
    print("=" * 60)
    print(f"  Base de datos: {DB_PATH}")
    print(f"  Exportaciones: {PROJECTS_DIR}")
    print(f"  LLM provider: {CONFIG['llm']['provider']}")
    print("=" * 60)

    # Permitir elegir servidor con variable de entorno:
    #   python app.py              -> dev (Flask/Werkzeug, con debug + autoreload)
    #   python app.py --prod       -> producción (Waitress)
    #   TST_SERVER=waitress python app.py   -> equivalente a --prod
    use_prod = "--prod" in sys.argv or os.environ.get("TST_SERVER") == "waitress"

    if use_prod:
        try:
            from waitress import serve
        except ImportError:
            print("  ERROR: waitress no instalado. Ejecuta: pip install waitress")
            sys.exit(1)
        host = os.environ.get("TST_HOST", "0.0.0.0")
        port = int(os.environ.get("TST_PORT", "5000"))
        threads = int(os.environ.get("TST_THREADS", "4"))
        print(f"  Servidor: Waitress (producción) · {host}:{port} · {threads} hilos")
        print(f"  Abre http://localhost:{port} en tu navegador")
        print("=" * 60)
        serve(app, host=host, port=port, threads=threads)
    else:
        print("  Servidor: Flask dev (debug) — usa --prod o TST_SERVER=waitress")
        print("             para entorno de producción.")
        print("  Abre http://localhost:5000 en tu navegador")
        print("=" * 60)
        app.run(host="0.0.0.0", port=5000, debug=True)

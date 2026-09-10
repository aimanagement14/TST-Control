"""
Todo Sobre Todo — Centro de producción de contenido
Aplicación Flask minimalista para preparar contenido antes de producción.

Arquitectura deliberadamente simple:
- Un solo archivo de aplicación
- SQLite sin ORM (más transparente)
- LLM opcional (manual por defecto, sin costos ni dependencias)
- Plantillas Jinja2
"""

import json
import logging
import os
import shutil
import sqlite3
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    g,
    has_app_context,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)

from services.manual import call_llm, llm_output_is_manual
from services.parsers import (
    count_words,
    parse_concept,
    parse_metadata,
    parse_research,
    parse_scenes,
    parse_script,
    parse_thumbnail,
)
from services.qc import run_qc, save_qc_issues
from services.sync import (
    delete_project_folder,
    safe_project_dir,
    sync_project_folder,
)

logging.basicConfig(
    level=os.environ.get("TST_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("tst")

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = BASE_DIR / "config.json"
DB_PATH = BASE_DIR / "workflow.db"
PROJECTS_DIR = BASE_DIR / "projects"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

load_dotenv(BASE_DIR / ".env", override=False)

with open(CONFIG_PATH, encoding="utf-8") as f:
    CONFIG = json.load(f)

PROJECTS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
_secret_key = os.environ.get("FLASK_SECRET_KEY") or CONFIG.get("app", {}).get("secret_key", "")
if not _secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY no definida. Exporta la variable de entorno "
        "(recomendado) o define 'app.secret_key' en config.json solo para dev local."
    )
app.secret_key = _secret_key
app.config["JSON_AS_ASCII"] = False
# TEMPLATES_AUTO_RELOAD: si no se fija, Flask lo iguala a `app.debug` —
# True en dev (autoreload al editar plantillas), False en prod (Waitress)
# para evitar el coste del filesystem check en cada render.

from blueprints.profiles import profiles_bp  # noqa: E402

app.register_blueprint(profiles_bp)


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

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    name TEXT NOT NULL,
    script_type TEXT NOT NULL DEFAULT 'short',
    format TEXT NOT NULL DEFAULT '9:16 vertical',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(project_id, key),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
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
    video_id INTEGER,
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
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
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
-- Tabla legacy de la etapa "Prompts visuales" (eliminada en 2026-08-29,
-- ver ADR-006). Se conserva solo por compatibilidad del esquema y porque
-- services/qc.py aun la lee; no recibe escrituras. El prompt visual vive
-- ahora en scenes.visual_description.

CREATE TABLE IF NOT EXISTS metadata_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    video_id INTEGER,
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
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS thumbnail_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    video_id INTEGER,
    script_type TEXT,
    prompt TEXT,
    updated_at TEXT,
    UNIQUE(project_id, script_type),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
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

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS profile_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    sys_prompt TEXT NOT NULL,
    user_prompt TEXT NOT NULL,
    updated_at TEXT,
    UNIQUE(profile_id, stage),
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS roadmap_stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    instruction TEXT,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    roadmap_stage_id INTEGER NOT NULL,
    instruction TEXT,
    response TEXT,
    updated_at TEXT,
    UNIQUE(project_id, roadmap_stage_id),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (roadmap_stage_id) REFERENCES roadmap_stages(id) ON DELETE CASCADE
);
"""


def get_db():
    """Obtiene una conexión a la base de datos.

    Dentro de un contexto de aplicación (petición, CLI) la conexión se
    cachea en ``flask.g`` y se cierra automáticamente por el teardown
    ``close_db``. Fuera de contexto (tests, scripts) abre una conexión
    transitoria que el caller cierra con ``with``.
    """
    if has_app_context():
        if "db" not in g:
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@app.teardown_appcontext
def close_db(exception=None):
    """Cierra la conexión cacheada en ``g`` al final de cada petición."""
    db = g.pop("db", None)
    if db is not None:
        if exception is not None:
            try:
                db.rollback()
            except Exception:
                # Rollback puede fallar si la conexión ya está rota; el
                # teardown no tiene más remedio que seguir y cerrar.
                log.warning("rollback falló en teardown: %s", db)
        db.close()


def init_db():
    """Inicializa el esquema y los datos por defecto."""
    with get_db() as conn:
        # WAL + busy_timeout reducen errores "database is locked" cuando
        # el runner ejecuta varios nodos en paralelo (lectores no bloquean).
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.executescript(SCHEMA)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT)"
        )
        _migrate_stage_prompts_to_profile_prompts(conn)
        # Perfil por defecto si no existe ninguno (necesario antes de la
        # migración al modelo genérico para que tenga a quién sembrar).
        cur = conn.execute("SELECT COUNT(*) AS n FROM profiles")
        if cur.fetchone()["n"] == 0:
            now = datetime.now().isoformat()
            conn.execute(
                """
                INSERT INTO profiles
                (name, content_type, audience, tone, style, mystery_level,
                 drama_level, narration_speed, platforms, is_default, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
                (
                    "Todo Sobre Todo / Misterio",
                    "Documental de misterio",
                    "Curiosos, aficionados a lo alternativo, 25-55 años",
                    "Serio con toques intrigantes, narrativo",
                    "Cinematográfico, contrastado, con toques conspiranoicos",
                    7,
                    6,
                    150,
                    json.dumps(["youtube", "shorts", "tiktok", "instagram", "facebook"]),
                    now,
                ),
            )
        _migrate_project_videos(conn)
        _migrate_qc_per_video(conn)
        _migrate_to_roadmap_model(conn)
        _ensure_roadmap_integrity(conn)
        conn.execute("DROP TABLE IF EXISTS profile_graph_nodes")
        conn.execute("DROP TABLE IF EXISTS node_executions")


# ---------------------------------------------------------------------------
# Migraciones opt-in (idempotentes, controladas por _schema_migrations)
# ---------------------------------------------------------------------------

_LEGACY_STAGE_PROMPTS_MIGRATION = "migrate_stage_prompts_to_profile_prompts"


def _migrate_stage_prompts_to_profile_prompts(conn):
    """Migra filas de `stage_prompts` (legacy, por proyecto) a `profile_prompts` (por perfil).

    Idempotente: solo se aplica una vez. Si la tabla legacy ya no existe,
    marca la migración como aplicada sin tocar datos.
    """
    row = conn.execute(
        "SELECT 1 FROM _schema_migrations WHERE name=?",
        (_LEGACY_STAGE_PROMPTS_MIGRATION,),
    ).fetchone()
    if row:
        return
    legacy = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='stage_prompts'"
    ).fetchone()
    if not legacy:
        conn.execute(
            "INSERT INTO _schema_migrations (name, applied_at) VALUES (?, ?)",
            (_LEGACY_STAGE_PROMPTS_MIGRATION, now_iso()),
        )
        return
    backup_path = str(DB_PATH) + ".bak"
    if not Path(backup_path).exists():
        shutil.copyfile(str(DB_PATH), backup_path)
    conn.execute("""
        INSERT OR IGNORE INTO profile_prompts
            (profile_id, stage, sys_prompt, user_prompt, updated_at)
        SELECT p.profile_id, sp.stage, sp.sys_prompt, sp.user_prompt, sp.updated_at
        FROM stage_prompts sp
        JOIN projects p ON p.id = sp.project_id
        WHERE p.profile_id IS NOT NULL
    """)
    conn.execute("DROP TABLE stage_prompts")
    conn.execute(
        "INSERT INTO _schema_migrations (name, applied_at) VALUES (?, ?)",
        (_LEGACY_STAGE_PROMPTS_MIGRATION, now_iso()),
    )


def _table_columns(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate_project_videos(conn):
    migration_exists = bool(
        conn.execute(
            "SELECT 1 FROM _schema_migrations WHERE name=?", (_VIDEOS_MIGRATION,)
        ).fetchone()
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            name TEXT NOT NULL,
            script_type TEXT NOT NULL DEFAULT 'short',
            format TEXT NOT NULL DEFAULT '9:16 vertical',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(project_id, key),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """
    )

    table_columns = {
        "scripts": _table_columns(conn, "scripts"),
        "metadata_records": _table_columns(conn, "metadata_records"),
        "thumbnail_records": _table_columns(conn, "thumbnail_records"),
    }
    if "video_id" not in table_columns["scripts"]:
        conn.execute("ALTER TABLE scripts ADD COLUMN video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE")
    if "video_id" not in table_columns["metadata_records"]:
        conn.execute(
            "ALTER TABLE metadata_records ADD COLUMN video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE"
        )
    if "video_id" not in table_columns["thumbnail_records"]:
        conn.execute(
            "ALTER TABLE thumbnail_records ADD COLUMN video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE"
        )

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_metadata_video_platform
        ON metadata_records(project_id, video_id, platform)
        WHERE video_id IS NOT NULL
    """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_thumbnail_video_script_type
        ON thumbnail_records(project_id, video_id, script_type)
        WHERE video_id IS NOT NULL
    """
    )

    if not migration_exists:
        project_ids = [
            row["id"]
            for row in conn.execute("SELECT id FROM projects ORDER BY id").fetchall()
        ]
        defaults = (
            ("long", "Video 5 min", "long", "16:9 horizontal"),
            ("short", "Video 1 min", "short", "9:16 vertical"),
        )
        for project_id in project_ids:
            next_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM videos WHERE project_id=?",
                (project_id,),
            ).fetchone()["n"]
            for key, name, script_type, video_format in defaults:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO videos
                        (project_id, key, name, script_type, format, sort_order, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        project_id,
                        key,
                        name,
                        script_type,
                        video_format,
                        next_order,
                        now_iso(),
                        now_iso(),
                    ),
                )
                next_order += 1

    for script in conn.execute(
        "SELECT id, project_id, type, video_id FROM scripts WHERE video_id IS NULL"
    ).fetchall():
        video = conn.execute(
            "SELECT id FROM videos WHERE project_id=? AND key=?",
            (script["project_id"], script["type"]),
        ).fetchone()
        if video:
            conn.execute("UPDATE scripts SET video_id=? WHERE id=?", (video["id"], script["id"]))

    legacy_metadata_video = {
        "youtube_long": "long",
        "facebook_long": "long",
        "youtube_short": "short",
        "reels_short": "short",
    }
    for record in conn.execute(
        "SELECT id, project_id, platform, video_id FROM metadata_records WHERE video_id IS NULL"
    ).fetchall():
        key = legacy_metadata_video.get(record["platform"])
        video = conn.execute(
            "SELECT id FROM videos WHERE project_id=? AND key=?",
            (record["project_id"], key),
        ).fetchone() if key else None
        if video:
            conn.execute("UPDATE metadata_records SET video_id=? WHERE id=?", (video["id"], record["id"]))

    for record in conn.execute(
        "SELECT id, project_id, script_type, video_id FROM thumbnail_records WHERE video_id IS NULL"
    ).fetchall():
        video = conn.execute(
            "SELECT id FROM videos WHERE project_id=? AND key=?",
            (record["project_id"], record["script_type"]),
        ).fetchone()
        if video:
            conn.execute("UPDATE thumbnail_records SET video_id=? WHERE id=?", (video["id"], record["id"]))

    conn.execute(
        "INSERT OR IGNORE INTO _schema_migrations (name, applied_at) VALUES (?, ?)",
        (_VIDEOS_MIGRATION, now_iso()),
    )


# ---------------------------------------------------------------------------
# Roadmap genérico (migración opt-in desde el esquema por etapa)
# ---------------------------------------------------------------------------

_ROADMAP_MIGRATION = "migrate_to_roadmap_model"
_VIDEOS_MIGRATION = "migrate_project_videos"
_QC_PER_VIDEO_MIGRATION = "migrate_qc_per_video"


def _migrate_qc_per_video(conn):
    """Añade el control de calidad por video.

    - ``projects.qc_state``: estado global del QC (``analyzed`` cuando
      se ha ejecutado el análisis con ``run_qc``; ``skipped`` cuando
      el usuario lo saltó). Permite distinguir un QC sin evaluar de
      un QC pasado sin issues.
    - ``qc_issues.video_id``: enlaza cada issue al video al que
      afecta. Los issues de proyecto (sin video concreto) quedan con
      ``NULL``.
    """
    row = conn.execute(
        "SELECT 1 FROM _schema_migrations WHERE name=?",
        (_QC_PER_VIDEO_MIGRATION,),
    ).fetchone()
    if row:
        return
    project_cols = _table_columns(conn, "projects")
    if "qc_state" not in project_cols:
        conn.execute("ALTER TABLE projects ADD COLUMN qc_state TEXT")
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='qc_issues'"
    ).fetchone():
        issue_cols = _table_columns(conn, "qc_issues")
        if "video_id" not in issue_cols:
            conn.execute(
                "ALTER TABLE qc_issues ADD COLUMN video_id INTEGER "
                "REFERENCES videos(id) ON DELETE CASCADE"
            )
    conn.execute(
        "INSERT OR IGNORE INTO _schema_migrations (name, applied_at) VALUES (?, ?)",
        (_QC_PER_VIDEO_MIGRATION, now_iso()),
    )

BACKUP_DIR = BASE_DIR / "backups"

DEFAULT_ROADMAP_STAGES = (
    "research",
    "concept",
    "scripts",
    "scenes",
    "metadata",
    "thumbnails",
    "qc",
)

ROADMAP_STAGE_LABELS = {
    "research": "Investigación",
    "concept": "Concepto",
    "scripts": "Guiones",
    "scenes": "Escenas",
    "metadata": "Metadata",
    "thumbnails": "Miniaturas",
    "qc": "Control de calidad",
}

ROADMAP_PROMPT_KEYS = {
    "research": ("research",),
    "concept": ("concept",),
    "scripts": ("script_long", "script_short"),
    "scenes": ("scenes",),
    "metadata": (
        "metadata_youtube_long",
        "metadata_facebook_long",
        "metadata_youtube_short",
        "metadata_reels_short",
    ),
    "thumbnails": ("thumbnail_long", "thumbnail_short"),
    "qc": (),
}


def _roadmap_instruction_for(conn, profile_id: int, stage_name: str) -> str:
    """Devuelve la instrucción inicial de una etapa, leída de ``profile_prompts`` o de ``config.json``.

    Si tanto ``sys_prompt`` como ``user_prompt`` están presentes los
    concatena en una sola instrucción; si solo uno está presente devuelve
    ese.

    Orden de búsqueda (Fase 1.2): primero la key del roadmap (que es como
    ``profile_prompts`` guarda las stages per-video `scripts`, `metadata`,
    `thumbnails`), luego las keys alternativas de CONFIG declaradas en
    ``ROADMAP_PROMPT_KEYS``.
    """
    candidate_keys = (stage_name,) + tuple(ROADMAP_PROMPT_KEYS.get(stage_name, ()))
    for key in candidate_keys:
        row = conn.execute(
            "SELECT sys_prompt, user_prompt FROM profile_prompts "
            "WHERE profile_id=? AND stage=?",
            (profile_id, key),
        ).fetchone()
        if row:
            sys_p = (row["sys_prompt"] or "").strip()
            user_p = (row["user_prompt"] or "").strip()
            if sys_p and user_p:
                return f"{sys_p}\n\n{user_p}"
            if sys_p:
                return sys_p
            if user_p:
                return user_p
        cfg = CONFIG.get("prompts", {}).get(key) or {}
        cfg_sys = (cfg.get("system") or "").strip()
        cfg_user = (cfg.get("format") or "").strip()
        if cfg_sys and cfg_user:
            return f"{cfg_sys}\n\n{cfg_user}"
        if cfg_sys:
            return cfg_sys
        if cfg_user:
            return cfg_user
    return ""


def _build_legacy_response(conn, project: dict, stage_name: str) -> str:
    """Combina los campos legacy de un proyecto en una respuesta Markdown para la etapa."""
    pid = project["id"]

    def _load_json(raw):
        try:
            value = json.loads(raw or "[]")
            return value if isinstance(value, list) else []
        except Exception:
            return []

    if stage_name == "research":
        row = conn.execute(
            "SELECT content, sources, facts, theories, unverified FROM research WHERE project_id=?",
            (pid,),
        ).fetchone()
        if not row or not (row["content"] or "").strip():
            return ""
        parts = ["# Investigación", "", row["content"].strip()]
        sources = _load_json(row["sources"])
        if sources:
            parts.append("")
            parts.append("## Fuentes")
            parts.append("")
            parts.extend(f"- {s}" for s in sources)
        return "\n".join(parts).strip() + "\n"

    if stage_name == "concept":
        row = conn.execute(
            "SELECT angle, thesis, key_points, emotional_hook, what_they_learn, what_they_feel, risks "
            "FROM concept WHERE project_id=?",
            (pid,),
        ).fetchone()
        if not row or not (row["angle"] or "").strip():
            return ""
        parts = [
            "# Concepto",
            "",
            "## Ángulo",
            row["angle"].strip(),
            "",
            "## Tesis",
            (row["thesis"] or "").strip(),
        ]
        kp = _load_json(row["key_points"])
        if kp:
            parts.append("")
            parts.append("## Puntos clave")
            parts.append("")
            parts.extend(f"1. {p}" for p in kp)
        if row["emotional_hook"]:
            parts.extend(["", "## Gancho emocional", row["emotional_hook"].strip()])
        wl = _load_json(row["what_they_learn"])
        if wl:
            parts.extend(["", "## Qué aprenden", ""])
            parts.extend(f"- {p}" for p in wl)
        wf = _load_json(row["what_they_feel"])
        if wf:
            parts.extend(["", "## Qué sienten", ""])
            parts.extend(f"- {p}" for p in wf)
        rk = _load_json(row["risks"])
        if rk:
            parts.extend(["", "## Riesgos", ""])
            parts.extend(f"- {p}" for p in rk)
        return "\n".join(parts).strip() + "\n"

    if stage_name == "scripts":
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT s.type, s.title, s.hook, s.context, s.development,
                       s.revelations, s.conclusion, s.cta, s.body_full,
                       v.name AS video_name
                FROM scripts s
                LEFT JOIN videos v ON v.id=s.video_id
                WHERE s.project_id=?
                """,
                (pid,),
            ).fetchall()
        ]
        if not rows:
            return ""
        parts = ["# Guiones", ""]
        for s in rows:
            label = s["video_name"] or ("Guion 5 min" if s["type"] == "long" else "Guion 1 min")
            parts.append(f"## {label}")
            parts.append("")
            if s.get("body_full"):
                parts.append(s["body_full"].strip())
            else:
                for heading, key in (
                    ("Hook", "hook"),
                    ("Contexto", "context"),
                    ("Desarrollo", "development"),
                    ("Revelaciones", "revelations"),
                    ("Conclusión", "conclusion"),
                    ("CTA", "cta"),
                ):
                    if s.get(key):
                        parts.extend([f"### {heading}", "", s[key].strip(), ""])
            parts.append("")
        return "\n".join(parts).strip() + "\n"

    if stage_name == "scenes":
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT scene_number, narration, visual_description, camera_movement, transition, "
                "duration_seconds FROM scenes WHERE project_id=? ORDER BY scene_number",
                (pid,),
            ).fetchall()
        ]
        if not rows:
            return ""
        parts = ["# Escenas", ""]
        for s in rows:
            parts.append(f"## ESCENA {s['scene_number']}")
            parts.append(f"**TEXTO AUDIO:** {(s.get('narration') or '').strip()}")
            parts.append(f"**IMAGEN:** {(s.get('visual_description') or '').strip()}")
            parts.append(
                f"_Cámara: {s.get('camera_movement') or ''} · "
                f"Transición: {s.get('transition') or ''} · "
                f"Duración: {s.get('duration_seconds') or 0}s_"
            )
            parts.append("")
        return "\n".join(parts).strip() + "\n"

    if stage_name == "metadata":
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT platform, titles, description, chapters, tags, hashtags, caption, hook, cta, "
                "on_screen_text FROM metadata_records WHERE project_id=?",
                (pid,),
            ).fetchall()
        ]
        if not rows:
            return ""
        parts = ["# Metadata", ""]
        for m in rows:
            parts.append(f"## {m['platform']}")
            parts.append("")
            if m.get("description"):
                parts.append(m["description"].strip())
                parts.append("")
            titles = _load_json(m["titles"])
            if titles:
                parts.append("### Títulos")
                parts.append("")
                parts.extend(f"{i}. {t}" for i, t in enumerate(titles, 1))
                parts.append("")
            chapters = _load_json(m["chapters"])
            if chapters:
                parts.append("### Capítulos")
                parts.append("")
                parts.extend(f"- {c}" for c in chapters)
                parts.append("")
            tags = _load_json(m["tags"])
            if tags:
                parts.append(f"### Tags: {', '.join(tags)}")
            hashtags = _load_json(m["hashtags"])
            if hashtags:
                parts.append(f"### Hashtags: {' '.join(hashtags)}")
            if m.get("caption"):
                parts.extend(["### Caption", "", m["caption"].strip(), ""])
            if m.get("hook"):
                parts.extend(["### Hook", "", m["hook"].strip(), ""])
            if m.get("cta"):
                parts.extend(["### CTA", "", m["cta"].strip(), ""])
            ost = _load_json(m["on_screen_text"])
            if ost:
                parts.append("### Texto en pantalla")
                parts.append("")
                parts.extend(f"{i}. {t}" for i, t in enumerate(ost, 1))
                parts.append("")
        return "\n".join(parts).strip() + "\n"

    if stage_name == "thumbnails":
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT script_type, prompt FROM thumbnail_records WHERE project_id=?",
                (pid,),
            ).fetchall()
        ]
        if not rows:
            return ""
        parts = ["# Miniaturas", ""]
        for t in rows:
            aspect = "16:9 (horizontal)" if t["script_type"] == "long" else "9:16 (vertical)"
            parts.append(f"## Miniatura {t['script_type']} — {aspect}")
            parts.append("")
            parts.append((t.get("prompt") or "").strip())
            parts.append("")
        return "\n".join(parts).strip() + "\n"

    if stage_name == "qc":
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT stage, severity, message FROM qc_issues WHERE project_id=? "
                "ORDER BY CASE severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, stage",
                (pid,),
            ).fetchall()
        ]
        if not rows:
            return ""
        parts = ["# Control de calidad", ""]
        for r in rows:
            parts.append(f"- [{r['severity']}] {r['stage']}: {r['message']}")
        return "\n".join(parts).strip() + "\n"

    return ""


def _migrate_to_roadmap_model(conn):
    """Migra el esquema al modelo genérico de hoja de ruta.

    Pasos (idempotentes, controlados por ``_schema_migrations``):

    1. Backup de ``workflow.db`` si no existe uno previo.
    2. Exporta ``profile_graph_nodes`` y ``node_executions`` a un JSON.
    3. Siembra ``roadmap_stages`` con las 7 etapas base por perfil,
       copiando la instrucción desde ``profile_prompts`` o ``config.json``.
    4. Para cada proyecto existente con ``profile_id``, inserta una
       fila en ``project_stages`` por cada ``roadmap_stage`` con la
       instrucción inicial y el ``response`` que ``_build_legacy_response``
       reconstruye desde las tablas legacy. ``INSERT OR IGNORE`` evita
       duplicar si la migración se ejecuta de nuevo.
    5. Elimina ``profile_graph_nodes`` y ``node_executions``.
    """
    row = conn.execute(
        "SELECT 1 FROM _schema_migrations WHERE name=?",
        (_ROADMAP_MIGRATION,),
    ).fetchone()
    if row:
        return

    BACKUP_DIR.mkdir(exist_ok=True)
    backup_stamp = now_iso().replace(":", "-").replace(".", "-")
    db_backup = BACKUP_DIR / f"workflow_{backup_stamp}.db.bak"
    if not db_backup.exists() and DB_PATH.exists():
        try:
            shutil.copyfile(str(DB_PATH), str(db_backup))
        except Exception:
            log.warning("[migrate_to_roadmap_model] no se pudo copiar el backup de DB")

    graph_nodes = []
    node_executions = []
    has_graph_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='profile_graph_nodes'"
    ).fetchone()
    if has_graph_table:
        graph_nodes = [dict(r) for r in conn.execute("SELECT * FROM profile_graph_nodes").fetchall()]
        node_executions = [dict(r) for r in conn.execute("SELECT * FROM node_executions").fetchall()]
    graph_payload = {
        "exported_at": now_iso(),
        "profile_graph_nodes": graph_nodes,
        "node_executions": node_executions,
    }
    graph_backup = BACKUP_DIR / f"graph_backup_{backup_stamp}.json"
    try:
        graph_backup.write_text(
            json.dumps(graph_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        log.warning("[migrate_to_roadmap_model] no se pudo escribir el backup JSON del grafo")

    now = now_iso()
    profiles = [
        dict(r)
        for r in conn.execute("SELECT id, name FROM profiles ORDER BY id").fetchall()
    ]
    for profile in profiles:
        for idx, stage_name in enumerate(DEFAULT_ROADMAP_STAGES):
            instruction = _roadmap_instruction_for(conn, profile["id"], stage_name)
            conn.execute(
                """
                INSERT INTO roadmap_stages
                    (profile_id, name, instruction, sort_order, is_active,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
                (
                    profile["id"],
                    stage_name,
                    instruction,
                    idx,
                    now,
                    now,
                ),
            )

    projects = [
        dict(r)
        for r in conn.execute(
            "SELECT id, name, topic, profile_id FROM projects ORDER BY id"
        ).fetchall()
    ]
    for project in projects:
        if not project.get("profile_id"):
            continue
        rs_rows = [
            dict(r)
            for r in conn.execute(
                "SELECT id, name, instruction FROM roadmap_stages WHERE profile_id=?",
                (project["profile_id"],),
            ).fetchall()
        ]
        for rs in rs_rows:
            response = _build_legacy_response(conn, project, rs["name"])
            conn.execute(
                """
                INSERT OR IGNORE INTO project_stages
                    (project_id, roadmap_stage_id, instruction, response, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    project["id"],
                    rs["id"],
                    rs.get("instruction") or "",
                    response,
                    now,
                ),
            )

    conn.execute("DROP TABLE IF EXISTS profile_graph_nodes")
    conn.execute("DROP TABLE IF EXISTS node_executions")

    conn.execute(
        "INSERT INTO _schema_migrations (name, applied_at) VALUES (?, ?)",
        (_ROADMAP_MIGRATION, now_iso()),
    )


def _ensure_roadmap_integrity(conn):
    """Reparador idempotente del modelo de hoja de ruta; se llama en cada arranque.

    No toca el marcador de ``_schema_migrations``: si la migración
    ``migrate_to_roadmap_model`` quedó registrada antes de haber sembrado
    ``roadmap_stages`` o ``project_stages``, este helper rellena los huecos
    sin alterar el resto del estado. Garantiza:

    - Cada perfil sin ninguna ``roadmap_stage`` recibe las siete etapas base
      (``DEFAULT_ROADMAP_STAGES``). Si el perfil ya tiene alguna etapa
      (p.ej. porque fue renombrada o personalizada) no se vuelve a sembrar
      para no crear duplicados. No modifica filas existentes, ni su
      ``instruction`` ni su ``is_active``.
    - Cada proyecto con ``profile_id`` tiene una ``project_stage`` por cada
      ``roadmap_stage`` del perfil, activa o inactiva. La ``instruction``
      inicial solo se escribe al crear la fila. La ``response`` se migra
      desde ``_build_legacy_response`` solo si la fila de ``project_stages``
      está vacía y la tabla legacy correspondiente tiene contenido. Nunca
      sobrescribe respuestas ni instrucciones ya editadas.
    """
    now = now_iso()
    profiles = [
        dict(r) for r in conn.execute("SELECT id FROM profiles ORDER BY id").fetchall()
    ]
    for profile in profiles:
        existing_names = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM roadmap_stages WHERE profile_id=?",
                (profile["id"],),
            ).fetchall()
        }
        if existing_names:
            continue
        for idx, stage_name in enumerate(DEFAULT_ROADMAP_STAGES):
            instruction = _roadmap_instruction_for(conn, profile["id"], stage_name)
            conn.execute(
                """
                INSERT INTO roadmap_stages
                    (profile_id, name, instruction, sort_order, is_active,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
                (profile["id"], stage_name, instruction, idx, now, now),
            )

    projects = [
        dict(r)
        for r in conn.execute(
            "SELECT id, name, topic, profile_id FROM projects "
            "WHERE profile_id IS NOT NULL ORDER BY id"
        ).fetchall()
    ]
    for project in projects:
        rs_rows = [
            dict(r)
            for r in conn.execute(
                "SELECT id, name, instruction FROM roadmap_stages WHERE profile_id=?",
                (project["profile_id"],),
            ).fetchall()
        ]
        for rs in rs_rows:
            existing = conn.execute(
                "SELECT id, response FROM project_stages "
                "WHERE project_id=? AND roadmap_stage_id=?",
                (project["id"], rs["id"]),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO project_stages
                        (project_id, roadmap_stage_id, instruction, response, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (
                        project["id"],
                        rs["id"],
                        rs.get("instruction") or "",
                        _build_legacy_response(conn, project, rs["name"]),
                        now,
                    ),
                )
                continue
            if (existing["response"] or "").strip():
                continue
            legacy_response = _build_legacy_response(conn, project, rs["name"])
            if legacy_response:
                conn.execute(
                    "UPDATE project_stages SET response=?, updated_at=? WHERE id=?",
                    (legacy_response, now, existing["id"]),
                )


# ---------------------------------------------------------------------------
# Prompts por perfil (graph foundation)
# ---------------------------------------------------------------------------


STAGE_ALIASES = {
    "scenes_short": "scenes",
    "scripts": "script_long",
    "thumbnails": "thumbnail_long",
}


def resolve_stage_prompt(profile_id: int | None, stage: str) -> tuple[str, str]:
    """Devuelve (sys_prompt, user_prompt) del perfil+stage o fallback a CONFIG.

    Si no hay fila en `profile_prompts` y `stage` está en CONFIG["prompts"],
    devuelve los strings canónicos. Si el stage no existe, devuelve ("", "")
    y registra un aviso por consola. Reconoce aliases declarados en
    ``STAGE_ALIASES`` para que distintos nombres del runner apunten al
    mismo prompt canónico.

    Aplica el mini-motor de plantillas ``{{profile.mystery_level}}`` etc.
    contra la fila del perfil activo. Si no hay perfil, devuelve el texto
    sin tocar.
    """
    from services.templates import render_profile

    stage_key = STAGE_ALIASES.get(stage, stage)
    raw_sys, raw_user = "", ""
    if profile_id is not None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT sys_prompt, user_prompt FROM profile_prompts "
                "WHERE profile_id=? AND stage=?",
                (profile_id, stage_key),
            ).fetchone()
            if row:
                raw_sys = row["sys_prompt"] or ""
                raw_user = row["user_prompt"] or ""
    if not raw_sys and not raw_user:
        cfg = CONFIG.get("prompts", {}).get(stage_key)
        if cfg:
            raw_sys = cfg.get("system", "")
            raw_user = cfg.get("format", "")
    if not raw_sys and not raw_user:
        log.warning("[resolve_stage_prompt] stage '%s' no existe en CONFIG['prompts']", stage)
        return "", ""
    if profile_id is None:
        return raw_sys, raw_user
    profile_row = get_profile(profile_id) if profile_id else None
    sys_p, _ = render_profile(raw_sys, profile_row)
    user_p, _ = render_profile(raw_user, profile_row)
    return sys_p, user_p


def save_profile_prompt(
    profile_id: int | None, stage: str, sys_prompt: str, user_prompt: str
) -> None:
    """UPSERT en `profile_prompts` por (profile_id, stage). No hace nada si profile_id es None."""
    if profile_id is None:
        return
    now = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO profile_prompts
                (profile_id, stage, sys_prompt, user_prompt, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, stage) DO UPDATE SET
                sys_prompt=excluded.sys_prompt,
                user_prompt=excluded.user_prompt,
                updated_at=excluded.updated_at
        """,
            (profile_id, stage, sys_prompt, user_prompt, now),
        )


def list_profile_prompts(profile_id: int | None) -> dict[str, dict[str, str]]:
    """Devuelve `{stage: {sys_prompt, user_prompt, updated_at}}` del perfil."""
    if profile_id is None:
        return {}
    with get_db() as conn:
        rows = conn.execute(
            "SELECT stage, sys_prompt, user_prompt, updated_at "
            "FROM profile_prompts WHERE profile_id=?",
            (profile_id,),
        ).fetchall()
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        out[row["stage"]] = {
            "sys_prompt": row["sys_prompt"],
            "user_prompt": row["user_prompt"],
            "updated_at": row["updated_at"],
        }
    return out


def get_default_prompts_from_config() -> dict[str, dict[str, str]]:
    """Devuelve `{stage: {system, format}}` desde CONFIG["prompts"]."""
    out: dict[str, dict[str, str]] = {}
    for stage, cfg in CONFIG.get("prompts", {}).items():
        out[stage] = {
            "system": cfg.get("system", ""),
            "format": cfg.get("format", ""),
        }
    return out


# ---------------------------------------------------------------------------
# Graph: constantes y CRUD de nodos por perfil
# ---------------------------------------------------------------------------

KNOWN_FIXED_NODE_KEYS = [
    "research",
    "concept",
    "script_long",
    "script_short",
    "scenes",
    "scenes_short",
    "metadata_youtube_long",
    "metadata_youtube_short",
    "metadata_facebook_long",
    "metadata_reels_short",
    "thumbnail_long",
    "thumbnail_short",
]

DEFAULT_NODE_LABELS = {
    "research": "Investigación",
    "concept": "Concepto",
    "script_long": "Guion 5 min",
    "script_short": "Guion 1 min",
    "scenes": "Escenas 5 min",
    "scenes_short": "Escenas 1 min",
    "metadata_youtube_long": "Metadata YouTube 5 min",
    "metadata_youtube_short": "Metadata YouTube 1 min",
    "metadata_facebook_long": "Metadata Facebook 5 min",
    "metadata_reels_short": "Metadata Reels 1 min",
    "thumbnail_long": "Miniatura 16:9",
    "thumbnail_short": "Miniatura 9:16",
}

DEFAULT_NODE_POSITIONS = {
    "research": (0.0, 0.0),
    "concept": (280.0, 0.0),
    "script_long": (560.0, 0.0),
    "script_short": (560.0, 180.0),
    "scenes": (840.0, 0.0),
    "scenes_short": (840.0, 180.0),
    "metadata_youtube_long": (1120.0, 0.0),
    "metadata_facebook_long": (1120.0, 90.0),
    "metadata_youtube_short": (1120.0, 180.0),
    "metadata_reels_short": (1120.0, 270.0),
    "thumbnail_long": (1400.0, 0.0),
    "thumbnail_short": (1400.0, 180.0),
}

DEFAULT_EDGES = [
    ("research", "concept"),
    ("concept", "script_long"),
    ("concept", "script_short"),
    ("script_long", "scenes"),
    ("script_short", "scenes_short"),
    ("script_long", "metadata_youtube_long"),
    ("script_long", "metadata_facebook_long"),
    ("script_short", "metadata_youtube_short"),
    ("script_short", "metadata_reels_short"),
    ("script_long", "thumbnail_long"),
    ("script_short", "thumbnail_short"),
]

MAX_OUTPUT_BYTES = 50 * 1024


def get_or_create_fixed_graph_nodes(profile_id: int | None) -> list[dict]:
    """Asegura las 9 filas fijas y devuelve todas como lista de dicts."""
    if not profile_id:
        return []
    with get_db() as conn:
        existing = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM profile_graph_nodes WHERE profile_id=? AND is_fixed=1",
                (profile_id,),
            ).fetchall()
        ]
        existing_keys = {row["node_key"] for row in existing}
        now = now_iso()
        for row in existing:
            if not row["sys_prompt"] or not row["user_prompt"]:
                default_sys = CONFIG["prompts"].get(row["node_key"], {}).get("system", "")
                default_user = CONFIG["prompts"].get(row["node_key"], {}).get("format", "")
                if default_sys and default_user:
                    conn.execute(
                        "UPDATE profile_graph_nodes "
                        "SET sys_prompt=?, user_prompt=?, updated_at=? "
                        "WHERE id=?",
                        (default_sys, default_user, now, row["id"]),
                    )
        for key in KNOWN_FIXED_NODE_KEYS:
            if key in existing_keys:
                continue
            x, y = DEFAULT_NODE_POSITIONS.get(key, (0.0, 0.0))
            default_sys = CONFIG["prompts"].get(key, {}).get("system", "")
            default_user = CONFIG["prompts"].get(key, {}).get("format", "")
            conn.execute(
                """
                INSERT INTO profile_graph_nodes
                    (profile_id, node_key, label, sys_prompt, user_prompt,
                     inputs_json, position_x, position_y, sort_order,
                     is_fixed, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
                (
                    profile_id,
                    key,
                    DEFAULT_NODE_LABELS.get(key, key),
                    default_sys,
                    default_user,
                    "[]",
                    x,
                    y,
                    KNOWN_FIXED_NODE_KEYS.index(key),
                    now,
                ),
            )
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM profile_graph_nodes "
                "WHERE profile_id=? AND is_fixed=1 ORDER BY sort_order, id",
                (profile_id,),
            ).fetchall()
        ]


def fetch_graph_nodes(profile_id: int | None) -> list[dict]:
    if not profile_id:
        return []
    with get_db() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM profile_graph_nodes WHERE profile_id=? ORDER BY sort_order, id",
                (profile_id,),
            ).fetchall()
        ]


def fetch_graph_edges_as_eedges(profile_id: int | None) -> list[dict]:
    """Devuelve aristas como [{id, source, target}] para el frontend.

    Solo emite aristas cuyos dos extremos existen como nodo del perfil,
    para evitar conexiones huérfanas que React Flow renderiza con warning.
    """
    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()
    rows: list[dict] = []
    if profile_id:
        with get_db() as conn:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT node_key, inputs_json FROM profile_graph_nodes WHERE profile_id=?",
                    (profile_id,),
                ).fetchall()
            ]
    valid_keys: set[str] = {r["node_key"] for r in rows}
    for src, tgt in DEFAULT_EDGES:
        if src not in valid_keys or tgt not in valid_keys:
            continue
        edges.append({"id": f"e_{src}_{tgt}", "source": src, "target": tgt})
        seen.add((src, tgt))
    for r in rows:
        try:
            inputs = json.loads(r["inputs_json"] or "[]")
        except Exception as e:
            # expected: inputs_json puede contener datos legacy malformados;
            # caemos a lista vacía y el grafo sigue funcionando.
            log.debug("inputs_json malformado en nodo %s: %s", r.get("node_key"), e)
            inputs = []
        if not isinstance(inputs, list):
            inputs = []
        for i, src in enumerate(inputs):
            if not src or src not in valid_keys:
                continue
            key = (str(src), r["node_key"])
            if key in seen:
                continue
            edges.append(
                {
                    "id": f"e_{src}_{r['node_key']}_{i}",
                    "source": str(src),
                    "target": r["node_key"],
                }
            )
            seen.add(key)
    return edges


def save_graph_node(
    profile_id: int,
    node_key: str,
    label: str,
    sys_prompt: str,
    user_prompt: str,
    inputs_json: str,
    position_x: float,
    position_y: float,
    is_fixed: bool,
) -> dict:
    """UPSERT en profile_graph_nodes; devuelve el dict persistido."""
    now = now_iso()
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM profile_graph_nodes WHERE profile_id=? AND node_key=?",
            (profile_id, node_key),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE profile_graph_nodes
                SET label=?, sys_prompt=?, user_prompt=?, inputs_json=?,
                    position_x=?, position_y=?, is_fixed=?, updated_at=?
                WHERE id=?
            """,
                (
                    label,
                    sys_prompt,
                    user_prompt,
                    inputs_json,
                    float(position_x),
                    float(position_y),
                    1 if is_fixed else 0,
                    now,
                    row["id"],
                ),
            )
            return dict(
                conn.execute(
                    "SELECT * FROM profile_graph_nodes WHERE id=?",
                    (row["id"],),
                ).fetchone()
            )
        conn.execute(
            """
            INSERT INTO profile_graph_nodes
                (profile_id, node_key, label, sys_prompt, user_prompt,
                 inputs_json, position_x, position_y, sort_order,
                 is_fixed, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                profile_id,
                node_key,
                label,
                sys_prompt,
                user_prompt,
                inputs_json,
                float(position_x),
                float(position_y),
                0,
                1 if is_fixed else 0,
                now,
            ),
        )
        new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        return dict(
            conn.execute(
                "SELECT * FROM profile_graph_nodes WHERE id=?",
                (new_id,),
            ).fetchone()
        )


def delete_graph_node(profile_id: int, node_key: str) -> bool:
    """Borra un nodo NO fijo. Devuelve True si se borró una fila."""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM profile_graph_nodes WHERE profile_id=? AND node_key=? AND is_fixed=0",
            (profile_id, node_key),
        )
        return cur.rowcount > 0


def update_graph_layout(profile_id: int, nodes_data: list[dict]) -> int:
    """Actualiza posiciones. Devuelve el número de filas tocadas."""
    count = 0
    now = now_iso()
    with get_db() as conn:
        for item in nodes_data:
            nk = item.get("node_key")
            if not nk:
                continue
            cur = conn.execute(
                "UPDATE profile_graph_nodes SET position_x=?, position_y=?, "
                "updated_at=? WHERE profile_id=? AND node_key=?",
                (
                    float(item.get("position_x", 0) or 0),
                    float(item.get("position_y", 0) or 0),
                    now,
                    profile_id,
                    str(nk),
                ),
            )
            count += cur.rowcount
    return count


def _interpolate_inputs(template: str, project_id: int, inputs: list[str]) -> str:
    """Sustituye {{ inputs.X }} con el último output del nodo X."""
    if not template or not inputs:
        return template or ""
    placeholders = ",".join("?" for _ in inputs)
    with get_db() as conn:
        try:
            rows = conn.execute(
                f"SELECT node_key, output FROM node_executions "
                f"WHERE project_id=? AND node_key IN ({placeholders}) "
                f"ORDER BY id DESC",
                (project_id, *inputs),
            ).fetchall()
        except Exception as e:
            # Si la consulta falla (p.ej. proyecto borrado entre
            # requests), seguimos con el template sin interpolar.
            log.warning(
                "_interpolate_inputs: no se pudo leer node_executions para project=%s inputs=%s: %s",
                project_id,
                inputs,
                e,
            )
            rows = []
    latest: dict[str, str] = {}
    for r in rows:
        latest.setdefault(r["node_key"], r["output"] or "")
    out = template
    for key in inputs:
        placeholder = "{{ inputs." + str(key) + " }}"
        out = out.replace(placeholder, latest.get(key, ""))
    return out


def _truncate_to_bytes(text: str, limit: int) -> str:
    if not text:
        return text or ""
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", "replace")


def _persist_scenes(conn, project_id: int, script_type: str, parsed: list, now: str) -> None:
    """Borra y reinserta las escenas del guion ``script_type`` del proyecto.

    Reutilizado por el runner de grafo para los nodos fijos ``scenes``
    (guion largo) y ``scenes_short`` (guion corto).
    """
    if not parsed:
        return
    target = conn.execute(
        """
        SELECT s.id
        FROM scripts s
        LEFT JOIN videos v ON v.id=s.video_id
        WHERE s.project_id=?
          AND (v.key=? OR (v.id IS NULL AND s.type=?))
        ORDER BY v.sort_order, s.id
        LIMIT 1
        """,
        (project_id, script_type, script_type),
    ).fetchone()
    sid = target["id"] if target else None
    if sid is None:
        return
    conn.execute(
        "DELETE FROM scenes WHERE project_id=? AND script_id=?",
        (project_id, sid),
    )
    wpm = 150
    proj = conn.execute(
        "SELECT profile_id FROM projects WHERE id=?",
        (project_id,),
    ).fetchone()
    if proj and proj["profile_id"]:
        prof = conn.execute(
            "SELECT narration_speed FROM profiles WHERE id=?",
            (proj["profile_id"],),
        ).fetchone()
        if prof and prof["narration_speed"]:
            wpm = prof["narration_speed"]
    total_words = sum(count_words(sc.get("narration_segment", "")) for sc in parsed)
    for sc in parsed:
        try:
            scene_num = int(sc.get("scene_number", 0) or 0)
        except (TypeError, ValueError) as e:
            # expected: scene_number puede venir no numerico del LLM;
            # caemos a 0 y el INSERT posterior lo reordena.
            log.debug("scene_number no numerico en escena: %s", e)
            scene_num = 0
        try:
            dur = int(sc.get("duration_seconds", 0) or 0)
        except (TypeError, ValueError) as e:
            log.debug("duration_seconds no numerico en escena: %s", e)
            dur = 0
        if not dur and total_words > 0:
            w = count_words(sc.get("narration_segment", ""))
            dur = max(1, round(w / wpm * 60))
        conn.execute(
            """
            INSERT INTO scenes (project_id, script_id, scene_number,
                narration, visual_description, camera_movement,
                transition, duration_seconds, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                project_id,
                sid,
                scene_num,
                sc.get("narration_segment", ""),
                sc.get("image_prompt", "") or sc.get("visual_description", ""),
                sc.get("camera_movement", "") or "",
                sc.get("transition", "") or "",
                dur,
                now,
            ),
        )


def _persist_fixed_result(project_id: int, node_key: str, raw: str) -> None:
    """Best-effort: persiste el raw en la tabla del stage correspondiente."""
    now = now_iso()
    with get_db() as conn:
        if node_key == "research":
            parsed = parse_research(raw)
            conn.execute(
                """
                INSERT INTO research (project_id, content, sources, facts,
                    theories, unverified, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    content=excluded.content,
                    sources=excluded.sources,
                    facts=excluded.facts,
                    theories=excluded.theories,
                    unverified=excluded.unverified,
                    updated_at=excluded.updated_at
            """,
                (
                    project_id,
                    parsed["content"] or raw,
                    json.dumps(parsed["sources"], ensure_ascii=False),
                    json.dumps(parsed["facts"], ensure_ascii=False),
                    json.dumps(parsed["theories"], ensure_ascii=False),
                    json.dumps(parsed["unverified"], ensure_ascii=False),
                    now,
                ),
            )
        elif node_key == "concept":
            parsed = parse_concept(raw)
            conn.execute(
                """
                INSERT INTO concept (project_id, angle, thesis, key_points,
                    emotional_hook, what_they_learn, what_they_feel,
                    risks, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    angle=excluded.angle,
                    thesis=excluded.thesis,
                    key_points=excluded.key_points,
                    emotional_hook=excluded.emotional_hook,
                    what_they_learn=excluded.what_they_learn,
                    what_they_feel=excluded.what_they_feel,
                    risks=excluded.risks,
                    updated_at=excluded.updated_at
            """,
                (
                    project_id,
                    parsed["angle"] or raw,
                    parsed["thesis"],
                    json.dumps(parsed["key_points"], ensure_ascii=False),
                    parsed["emotional_hook"],
                    json.dumps(parsed["what_they_learn"], ensure_ascii=False),
                    json.dumps(parsed["what_they_feel"], ensure_ascii=False),
                    json.dumps(parsed["risks"], ensure_ascii=False),
                    now,
                ),
            )
        elif node_key in ("script_long", "script_short"):
            stype = "long" if node_key == "script_long" else "short"
            script_data = parse_script(raw, stype)
            body = script_data["body_full"] or raw
            wc = count_words(body)
            video = conn.execute(
                "SELECT id FROM videos WHERE project_id=? AND key=?",
                (project_id, stype),
            ).fetchone()
            video_id = video["id"] if video else None
            existing = conn.execute(
                "SELECT id FROM scripts WHERE project_id=? AND video_id=?",
                (project_id, video_id),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE scripts SET title=?, hook=?, context=?, development=?,
                        revelations=?, conclusion=?, cta=?, body_full=?,
                        word_count=?, video_id=?, updated_at=? WHERE id=?
                """,
                    (
                        script_data["title"],
                        script_data["hook"],
                        script_data["context"],
                        script_data["development"],
                        script_data["revelations"],
                        script_data["conclusion"],
                        script_data["cta"],
                        body,
                        wc,
                        video_id,
                        now,
                        existing["id"],
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO scripts (project_id, video_id, type, title, hook, context,
                        development, revelations, conclusion, cta, body_full,
                        word_count, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        project_id,
                        video_id,
                        stype,
                        script_data["title"],
                        script_data["hook"],
                        script_data["context"],
                        script_data["development"],
                        script_data["revelations"],
                        script_data["conclusion"],
                        script_data["cta"],
                        body,
                        wc,
                        now,
                    ),
                )
        elif node_key in ("scenes", "scenes_short"):
            script_type = "long" if node_key == "scenes" else "short"
            _persist_scenes(conn, project_id, script_type, parse_scenes(raw) or [], now)
        elif node_key in (
            "metadata_youtube_long",
            "metadata_youtube_short",
            "metadata_facebook_long",
            "metadata_reels_short",
        ):
            platform = {
                "metadata_youtube_long": "youtube_long",
                "metadata_youtube_short": "youtube_short",
                "metadata_facebook_long": "facebook_long",
                "metadata_reels_short": "reels_short",
            }[node_key]
            metadata_data = parse_metadata(raw, platform)
            video = conn.execute(
                "SELECT id FROM videos WHERE project_id=? AND key=?",
                (project_id, "long" if "long" in platform else "short"),
            ).fetchone()
            video_id = video["id"] if video else None
            existing = conn.execute(
                "SELECT id FROM metadata_records WHERE project_id=? AND video_id=? AND platform=?",
                (project_id, video_id, platform),
            ).fetchone()
            fields = (
                json.dumps(metadata_data["titles"], ensure_ascii=False),
                metadata_data["description"],
                json.dumps(metadata_data["chapters"], ensure_ascii=False),
                json.dumps(metadata_data["tags"], ensure_ascii=False),
                json.dumps(metadata_data["hashtags"], ensure_ascii=False),
                metadata_data["caption"],
                metadata_data["hook"],
                metadata_data["cta"],
                json.dumps(metadata_data["on_screen_text"], ensure_ascii=False),
            )
            if existing:
                conn.execute(
                    """
                    UPDATE metadata_records SET titles=?, description=?,
                        chapters=?, tags=?, hashtags=?, caption=?, hook=?, cta=?,
                        on_screen_text=?, video_id=?, updated_at=? WHERE id=?
                """,
                    (*fields, video_id, now, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO metadata_records (project_id, video_id, platform,
                        titles, description, chapters, tags, hashtags, caption,
                        hook, cta, on_screen_text, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (project_id, video_id, platform, *fields, now),
                )
        elif node_key in ("thumbnail_long", "thumbnail_short"):
            stype = "long" if node_key == "thumbnail_long" else "short"
            thumbnail_data = parse_thumbnail(raw, stype)
            prompt_text = (thumbnail_data.get("prompt") or "").strip() or raw.strip()
            video = conn.execute(
                "SELECT id FROM videos WHERE project_id=? AND key=?",
                (project_id, stype),
            ).fetchone()
            video_id = video["id"] if video else None
            existing = conn.execute(
                "SELECT id FROM thumbnail_records WHERE project_id=? AND video_id=?",
                (project_id, video_id),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE thumbnail_records SET prompt=?, script_type=?, video_id=?, updated_at=? WHERE id=?",
                    (prompt_text, stype, video_id, now, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO thumbnail_records
                        (project_id, video_id, script_type, prompt, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (project_id, video_id, stype, prompt_text, now),
                )


def _load_first_script(project_id: int, script_type: str) -> dict:
    """Devuelve el primer guion del tipo pedido o un dict vacío con campos clave."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT s.*
            FROM scripts s
            LEFT JOIN videos v ON v.id=s.video_id
            WHERE s.project_id=?
              AND (v.key=? OR (v.id IS NULL AND s.type=?))
            ORDER BY v.sort_order, s.id
            LIMIT 1
            """,
            (project_id, script_type, script_type),
        ).fetchone()
        if row:
            return dict(row)
    return {
        "title": "",
        "hook": "",
        "body_full": "",
        "word_count": 0,
        "context": "",
        "development": "",
        "revelations": "",
        "conclusion": "",
        "cta": "",
    }


def _build_user_msg_for_fixed(
    project_id: int, profile: dict | None, project: dict, node_key: str
) -> str:
    """Construye el user_msg para un nodo fijo."""
    if node_key == "research":
        _, user_msg = build_research_prompt(project, profile)
        return user_msg
    if node_key == "concept":
        with get_db() as conn:
            research_obj = fetch_optional_dict(
                conn,
                "SELECT * FROM research WHERE project_id=?",
                (project_id,),
            )
        _, user_msg = build_concept_prompt(project, profile, research_obj)
        return user_msg
    if node_key == "script_long":
        with get_db() as conn:
            research_obj = fetch_optional_dict(
                conn,
                "SELECT * FROM research WHERE project_id=?",
                (project_id,),
            )
            concept_obj = fetch_optional_dict(
                conn,
                "SELECT * FROM concept WHERE project_id=?",
                (project_id,),
            )
        _, user_msg = build_script_prompt(
            project,
            profile,
            research_obj,
            concept_obj,
            "long",
        )
        return user_msg
    if node_key == "script_short":
        with get_db() as conn:
            research_obj = fetch_optional_dict(
                conn,
                "SELECT * FROM research WHERE project_id=?",
                (project_id,),
            )
            concept_obj = fetch_optional_dict(
                conn,
                "SELECT * FROM concept WHERE project_id=?",
                (project_id,),
            )
        _, user_msg = build_script_prompt(
            project,
            profile,
            research_obj,
            concept_obj,
            "short",
        )
        return user_msg
    if node_key == "scenes":
        script = _load_first_script(project_id, "long")
        _, user_msg = build_scenes_prompt(project, profile, script)
        return user_msg
    if node_key == "scenes_short":
        script = _load_first_script(project_id, "short")
        _, user_msg = build_scenes_prompt(project, profile, script)
        return user_msg
    if node_key == "metadata_youtube_long":
        script = _load_first_script(project_id, "long")
        _, user_msg = build_metadata_prompt(project, profile, script, "youtube_long")
        return user_msg
    if node_key == "metadata_facebook_long":
        script = _load_first_script(project_id, "long")
        _, user_msg = build_metadata_prompt(project, profile, script, "facebook_long")
        return user_msg
    if node_key == "metadata_youtube_short":
        script = _load_first_script(project_id, "short")
        _, user_msg = build_metadata_prompt(project, profile, script, "youtube_short")
        return user_msg
    if node_key == "metadata_reels_short":
        script = _load_first_script(project_id, "short")
        _, user_msg = build_metadata_prompt(project, profile, script, "reels_short")
        return user_msg
    if node_key == "thumbnail_long":
        script = _load_first_script(project_id, "long")
        _, user_msg = build_thumbnail_prompt(project, profile, script, "long")
        return user_msg
    if node_key == "thumbnail_short":
        script = _load_first_script(project_id, "short")
        _, user_msg = build_thumbnail_prompt(project, profile, script, "short")
        return user_msg
    raise ValueError(f"Nodo fijo desconocido: {node_key}")


def execute_graph_node(project_id: int, node_key: str) -> dict:
    """Ejecuta un nodo del grafo. Devuelve dict listo para JSON."""
    t0 = time.monotonic()
    try:
        with get_db() as conn:
            proj = conn.execute(
                "SELECT * FROM projects WHERE id=?",
                (project_id,),
            ).fetchone()
            if proj is None:
                return {"ok": False, "status": "error", "error": "Proyecto no encontrado"}
            project = dict(proj)
        profile = get_profile(project["profile_id"]) or get_default_profile()
        profile_id = profile["id"] if profile else None
        node_row = None
        if profile_id:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT * FROM profile_graph_nodes WHERE profile_id=? AND node_key=?",
                    (profile_id, node_key),
                ).fetchone()
            node_row = dict(row) if row else None

        if node_key in KNOWN_FIXED_NODE_KEYS:
            sys_p, _ = resolve_stage_prompt(profile_id, node_key)
            user_msg = _build_user_msg_for_fixed(
                project_id,
                profile,
                project,
                node_key,
            )
            raw = call_llm(sys_p, user_msg)
            _persist_fixed_result(project_id, node_key, raw)
        else:
            if not node_row:
                return {"ok": False, "status": "error", "error": "Nodo personalizado no encontrado"}
            sys_p = node_row.get("sys_prompt") or ""
            template = node_row.get("user_prompt") or ""
            try:
                inputs = json.loads(node_row.get("inputs_json") or "[]")
            except Exception as e:
                # expected: inputs_json puede contener datos malformados;
                # caemos a lista vacía y la ejecucion sigue sin inputs.
                log.debug("inputs_json malformado en nodo custom: %s", e)
                inputs = []
            if not isinstance(inputs, list):
                inputs = []
            user_msg = _interpolate_inputs(template, project_id, inputs)
            raw = call_llm(sys_p, user_msg)

        raw = _truncate_to_bytes(raw, MAX_OUTPUT_BYTES)
        duration_ms = int((time.monotonic() - t0) * 1000)
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO node_executions
                    (project_id, node_key, output, status, duration_ms, created_at)
                VALUES (?, ?, ?, 'ok', ?, ?)
            """,
                (project_id, node_key, raw, duration_ms, now_iso()),
            )
            last = conn.execute(
                "SELECT id, status, duration_ms, created_at FROM node_executions "
                "WHERE id=last_insert_rowid()"
            ).fetchone()
        return {
            "ok": True,
            "status": "ok",
            "output": raw,
            "node_executions": dict(last) if last else {},
        }
    except Exception as e:
        log.exception("execute_graph_node falló project=%s node=%s", project_id, node_key)
        msg = str(e)[:4096]
        try:
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO node_executions
                        (project_id, node_key, output, status, created_at)
                    VALUES (?, ?, ?, 'error', ?)
                """,
                    (project_id, node_key, msg, now_iso()),
                )
        except Exception as persist_err:
            # No podemos hacer mucho más; logueamos y devolvemos el
            # error original al caller para que lo muestre al usuario.
            log.error("no se pudo persistir el error en node_executions: %s", persist_err)
        return {"ok": False, "status": "error", "error": str(e)[:500]}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def load_roadmap_stages(profile_id: int | None) -> list[dict]:
    """Devuelve las etapas activas del perfil ordenadas por ``sort_order``."""
    if not profile_id:
        return []
    with get_db() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM roadmap_stages WHERE profile_id=? AND is_active=1 "
                "ORDER BY sort_order, id",
                (profile_id,),
            ).fetchall()
        ]


def load_project_stages(project_id: int) -> list[dict]:
    """Devuelve las ``project_stages`` del proyecto con la info de su ``roadmap_stage``."""
    with get_db() as conn:
        return [
            dict(r)
            for r in conn.execute(
                """
                SELECT ps.id AS id, ps.project_id, ps.roadmap_stage_id,
                       ps.instruction, ps.response, ps.updated_at,
                       rs.profile_id, rs.name AS stage_name, rs.sort_order,
                       rs.is_active, rs.created_at AS rs_created_at
                FROM project_stages ps
                JOIN roadmap_stages rs ON rs.id = ps.roadmap_stage_id
                WHERE ps.project_id=?
                ORDER BY rs.sort_order, rs.id
            """,
                (project_id,),
            ).fetchall()
        ]


def sync_project_stages_for_project(project_id: int) -> list[dict]:
    """Asegura que el proyecto tiene una ``project_stage`` por cada ``roadmap_stage`` activa del perfil.

    Crea las filas activas que falten. Conserva las filas de etapas
    desactivadas (``is_active=0``) para no perder respuestas ya escritas.
    Sólo elimina filas cuyo ``roadmap_stage_id`` ya no existe en
    ``roadmap_stages`` (etapa borrada del roadmap). Devuelve la lista
    actualizada de ``project_stages``.
    """
    with get_db() as conn:
        project = conn.execute(
            "SELECT profile_id FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        if not project or not project["profile_id"]:
            return []
        profile_id = project["profile_id"]
        active_roadmap = [
            dict(r)
            for r in conn.execute(
                "SELECT id, instruction FROM roadmap_stages "
                "WHERE profile_id=? AND is_active=1",
                (profile_id,),
            ).fetchall()
        ]
        all_roadmap_ids = {
            r["id"]
            for r in conn.execute(
                "SELECT id FROM roadmap_stages WHERE profile_id=?",
                (profile_id,),
            ).fetchall()
        }
        existing_rows = [
            dict(r)
            for r in conn.execute(
                "SELECT id, roadmap_stage_id FROM project_stages WHERE project_id=?",
                (project_id,),
            ).fetchall()
        ]
        existing_ids = {r["roadmap_stage_id"] for r in existing_rows}
        now = now_iso()
        for rs in active_roadmap:
            if rs["id"] in existing_ids:
                continue
            conn.execute(
                """
                INSERT INTO project_stages
                    (project_id, roadmap_stage_id, instruction, response, updated_at)
                VALUES (?, ?, ?, '', ?)
            """,
                (project_id, rs["id"], rs["instruction"], now),
            )
        for ps in existing_rows:
            if ps["roadmap_stage_id"] not in all_roadmap_ids:
                conn.execute("DELETE FROM project_stages WHERE id=?", (ps["id"],))
    return load_project_stages(project_id)


def sync_profile_projects(profile_id: int, *, sync_folder: bool = True) -> int:
    """Sincroniza ``project_stages`` y, opcionalmente, la carpeta de todos los proyectos del perfil.

    Pensado para llamarse desde ``blueprints/profiles`` tras ``create`` o
    ``update``. Los errores en un proyecto se registran pero no detienen
    el resto. Devuelve el número de proyectos sincronizados correctamente.
    """
    with get_db() as conn:
        project_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM projects WHERE profile_id=?", (profile_id,)
            ).fetchall()
        ]
    synced = 0
    for pid in project_ids:
        try:
            sync_project_stages_for_project(pid)
            if sync_folder:
                sync_project_folder(pid)
            synced += 1
        except Exception:
            log.exception("[sync_profile_projects] pid=%s profile=%s", pid, profile_id)
    return synced


def build_stage_context(project_id: int, stage_id: int) -> str:
    """Concatena en Markdown las respuestas de las etapas anteriores para alimentar al LLM."""
    stages = load_project_stages(project_id)
    current = next((s for s in stages if s["id"] == stage_id), None)
    if not current:
        return ""
    parts: list[str] = []
    for s in stages:
        if s["sort_order"] >= current["sort_order"]:
            break
        response = (s.get("response") or "").strip()
        if not response:
            continue
        label = ROADMAP_STAGE_LABELS.get(s["stage_name"], s["stage_name"])
        parts.append(f"## {label}\n\n{response}")
    return "\n\n---\n\n".join(parts)


def generate_stage_response(project_id: int, stage_id: int) -> tuple[str, str, str]:
    """Llama al LLM con la instrucción del proyecto y el contexto acumulado. Devuelve (sys, raw, user)."""
    stages = load_project_stages(project_id)
    current = next((s for s in stages if s["id"] == stage_id), None)
    if not current:
        return "", "", ""
    project = fetch_project_or_404(project_id)
    profile = get_profile(project["profile_id"])
    sys_p = (current.get("instruction") or "").strip()
    label = ROADMAP_STAGE_LABELS.get(current["stage_name"], current["stage_name"])
    user_parts = [
        f"Tema: {project['topic']}",
        "Canal: Todo Sobre Todo",
    ]
    if profile:
        user_parts.append(f"Tipo de contenido: {profile.get('content_type', '') or 'documental'}")
        user_parts.append(f"Tono: {profile.get('tone', '') or 'serio'}")
        user_parts.append(f"Estilo: {profile.get('style', '') or 'cinematográfico'}")
        user_parts.append(f"Nivel de misterio: {profile.get('mystery_level', 5)}/10")
    context = build_stage_context(project_id, stage_id)
    if context:
        user_parts.extend(["", "Contexto de etapas anteriores:", "", context])
    user_parts.extend(["", f"Etapa actual: {label}."])
    user_msg = "\n".join(user_parts)
    raw = call_llm(sys_p, user_msg)
    return sys_p, raw, user_msg


def recompute_project_status(conn, project_id: int) -> None:
    """Recalcula ``projects.status`` según las ``project_stages`` activas.

    Devuelve ``'ready'`` si todas las etapas activas del proyecto tienen
    ``response`` no vacía. Si falta alguna, degrada el estado a
    ``'in_progress'`` para que limpiar una respuesta saque al proyecto
    de ``ready``. No depende de los scripts legacy de cada etapa.
    """
    total_row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM project_stages ps
        JOIN roadmap_stages rs ON rs.id = ps.roadmap_stage_id
        WHERE ps.project_id=? AND rs.is_active=1
        """,
        (project_id,),
    ).fetchone()
    total = total_row["n"] if total_row else 0
    if total == 0:
        return
    done_row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM project_stages ps
        JOIN roadmap_stages rs ON rs.id = ps.roadmap_stage_id
        WHERE ps.project_id=? AND rs.is_active=1
          AND ps.response IS NOT NULL AND TRIM(ps.response) != ''
        """,
        (project_id,),
    ).fetchone()
    done = done_row["n"] if done_row else 0
    if done < total:
        conn.execute(
            "UPDATE projects SET status='in_progress', updated_at=? WHERE id=?",
            (now_iso(), project_id),
        )
        return
    conn.execute(
        "UPDATE projects SET status='ready', updated_at=? WHERE id=?",
        (now_iso(), project_id),
    )


def project_stage_status(project):
    """Devuelve ``{stage_name: True/False}`` con el estado de cada etapa activa del proyecto.

    Las etapas 01 (Investigación) y 02 (Concepto) son de proyecto; las
    etapas 03-07 (Guiones, Escenas, Metadata, Miniaturas, QC) viven por
    video: la etapa está hecha sólo cuando **todos** los videos del
    proyecto la tienen completa. Si el proyecto no tiene filas en la
    tabla ``videos`` se cae a la lógica legacy basada en respuesta.
    """
    from services.stages import video_stage_status

    pid = project["id"]
    stages: dict[str, bool] = {}
    active_stages: set[str] = set()
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT rs.name AS name, ps.response AS response
            FROM project_stages ps
            JOIN roadmap_stages rs ON rs.id = ps.roadmap_stage_id
            WHERE ps.project_id=? AND rs.is_active=1
            """,
            (pid,),
        ).fetchall()
    for r in rows:
        active_stages.add(r["name"])
        stages[r["name"]] = bool((r["response"] or "").strip())

    def _has(query: str, params: tuple) -> bool:
        with get_db() as conn:
            return bool(conn.execute(query, params).fetchone())

    if not stages.get("research"):
        stages["research"] = _has(
            "SELECT 1 FROM research WHERE project_id=? AND content IS NOT NULL AND content != ''",
            (pid,),
        )
    if not stages.get("concept"):
        stages["concept"] = _has(
            "SELECT 1 FROM concept WHERE project_id=? AND angle IS NOT NULL AND angle != ''",
            (pid,),
        )

    videos_state = video_stage_status(pid)
    has_videos = bool(videos_state)
    for stage_key in ("scripts", "scenes", "metadata", "thumbnails", "qc"):
        if stage_key not in active_stages:
            continue
        if stages.get(stage_key):
            continue
        if has_videos:
            stages[stage_key] = all(
                v["stages"][stage_key] for v in videos_state
            )
            continue
        # Fallback legacy: la fila de ``videos`` se siembra más adelante
        # o el proyecto es sintético; conservar el cálculo histórico.
        if stage_key == "scripts":
            videos = load_project_videos(pid)
            with get_db() as conn:
                complete = conn.execute(
                    """
                    SELECT COUNT(DISTINCT COALESCE(v.key, s.type)) AS n
                    FROM scripts s
                    LEFT JOIN videos v ON v.id=s.video_id
                    WHERE s.project_id=? AND (s.body_full IS NOT NULL AND TRIM(s.body_full) != '')
                    """,
                    (pid,),
                ).fetchone()["n"]
            stages["scripts"] = bool(videos) and complete == len(videos)
        elif stage_key == "scenes":
            videos = load_project_videos(pid)
            with get_db() as conn:
                complete = conn.execute(
                    """
                    SELECT COUNT(DISTINCT CASE WHEN sc.id IS NULL THEN 'legacy'
                                                  ELSE COALESCE(v.key, sc.type) END) AS n
                    FROM scenes s
                    LEFT JOIN scripts sc ON sc.id=s.script_id
                    LEFT JOIN videos v ON v.id=sc.video_id
                    WHERE s.project_id=?
                    """,
                    (pid,),
                ).fetchone()["n"]
            stages["scenes"] = bool(videos) and complete == len(videos)
        elif stage_key == "metadata":
            videos = load_project_videos(pid)
            with get_db() as conn:
                complete = conn.execute(
                    """
                    SELECT COUNT(DISTINCT COALESCE(v.key,
                        CASE WHEN m.platform LIKE '%short%' THEN 'short' ELSE 'long' END)) AS n
                    FROM metadata_records m
                    LEFT JOIN videos v ON v.id=m.video_id
                    WHERE m.project_id=?
                    """,
                    (pid,),
                ).fetchone()["n"]
            stages["metadata"] = bool(videos) and complete == len(videos)
        elif stage_key == "thumbnails":
            videos = load_project_videos(pid)
            with get_db() as conn:
                complete = conn.execute(
                    """
                    SELECT COUNT(DISTINCT COALESCE(v.key, t.script_type)) AS n
                    FROM thumbnail_records t
                    LEFT JOIN videos v ON v.id=t.video_id
                    WHERE t.project_id=? AND t.prompt IS NOT NULL AND TRIM(t.prompt) != ''
                    """,
                    (pid,),
                ).fetchone()["n"]
            stages["thumbnails"] = bool(videos) and complete == len(videos)
    return stages


# ---------------------------------------------------------------------------
# Pipeline: orden de etapas, estado legible y siguiente acción
# ---------------------------------------------------------------------------

PIPELINE_STAGES = (
    {
        "key": "research",
        "num": "01",
        "label": "Investigación",
        "short": "Investigación",
        "endpoint": "research",
        "hint": "Hechos, fuentes y teorías",
    },
    {
        "key": "concept",
        "num": "02",
        "label": "Concepto",
        "short": "Concepto",
        "endpoint": "concept",
        "hint": "Ángulo, tesis y gancho",
    },
    {
        "key": "scripts_long",
        "num": "03",
        "label": "Guion 5 min",
        "short": "Guion 5 min",
        "endpoint": "scripts",
        "hint": "Documental completo",
    },
    {
        "key": "scripts_short",
        "num": "04",
        "label": "Guion 1 min",
        "short": "Guion 1 min",
        "endpoint": "scripts",
        "hint": "Versión vertical",
    },
    {
        "key": "scenes",
        "num": "05",
        "label": "Escenas",
        "short": "Escenas",
        "endpoint": "scenes",
        "hint": "Secuencia visual",
    },
    {
        "key": "metadata",
        "num": "06",
        "label": "Metadata",
        "short": "Metadata",
        "endpoint": "metadata",
        "hint": "Títulos, tags y CTA",
    },
    {
        "key": "thumbnails",
        "num": "07",
        "label": "Miniaturas",
        "short": "Miniaturas",
        "endpoint": "thumbnails",
        "hint": "Prompts visuales de portada",
    },
    {
        "key": "qc",
        "num": "08",
        "label": "Control de calidad",
        "short": "Calidad",
        "endpoint": "qc",
        "hint": "Revisión antes de exportar",
    },
)

PAGE_ORDER = ("research", "concept", "scripts", "scenes", "metadata", "thumbnails", "qc", "export")

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
            """
            SELECT s.word_count
            FROM scripts s
            LEFT JOIN videos v ON v.id=s.video_id
            WHERE s.project_id=? AND (v.key='long' OR (v.id IS NULL AND s.type='long'))
            ORDER BY v.sort_order, s.id
            LIMIT 1
            """,
            (project["id"],),
        ).fetchone()
        if row is None:
            row = conn.execute(
                """
                SELECT s.word_count
                FROM scripts s
                LEFT JOIN videos v ON v.id=s.video_id
                WHERE s.project_id=?
                ORDER BY v.sort_order, s.id
                LIMIT 1
                """,
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

    `current` es el ``id`` de la ``project_stage`` activa (no el nombre
    de la página). Las celdas se construyen dinámicamente desde las
    ``roadmap_stages`` activas del perfil del proyecto y enlazan a la
    ruta genérica ``project_stage``. Para etapas per-video (Guiones,
    Escenas, Metadata, Miniaturas y QC) la celda adjunta
    ``cell.videos`` con el desglose por video, que es lo que alimenta
    el contador ``X/Y`` del stepper y la Hoja de ruta expandida.
    """
    from services.stages import (
        PER_VIDEO_STAGES,
        attach_breakdown_urls,
        stage_breakdown_for,
    )

    stages_dict = dict(project.get("stages") or project_stage_status(project))
    profile_id = project.get("profile_id")
    roadmap = load_roadmap_stages(profile_id)

    cells: list[dict] = []
    pending = None
    prev_step = None
    next_step = None
    current_index = None
    with get_db() as conn:
        ps_index = {
            r["roadmap_stage_id"]: r["id"]
            for r in conn.execute(
                "SELECT id, roadmap_stage_id FROM project_stages WHERE project_id=?",
                (project["id"],),
            ).fetchall()
        }

    for idx, rs in enumerate(roadmap):
        stage_id = ps_index.get(rs["id"])
        label = ROADMAP_STAGE_LABELS.get(rs["name"], rs["name"])
        is_per_video = rs["name"] in PER_VIDEO_STAGES
        breakdown = stage_breakdown_for(project["id"], rs["name"]) if is_per_video else []
        attach_breakdown_urls(project["id"], breakdown)
        cell = {
            "id": stage_id,
            "key": rs["name"],
            "num": f"{idx + 1:02d}",
            "label": label,
            "short": label,
            "hint": "",
            "done": bool(stages_dict.get(rs["name"])),
            "current": stage_id is not None and stage_id == current,
            "per_video": is_per_video,
            "videos": breakdown,
            "videos_done": sum(1 for v in breakdown if v["done"]),
            "videos_total": len(breakdown),
            "url": (
                url_for("project_stage", project_id=project["id"], stage_id=stage_id)
                if stage_id is not None
                else url_for("view_project", project_id=project["id"])
            ),
        }
        if not cell["done"] and pending is None:
            pending = cell
        if stage_id is not None and stage_id == current:
            current_index = idx
        cells.append(cell)

    if current_index is not None:
        if current_index > 0 and cells[current_index - 1]["id"] is not None:
            prev = cells[current_index - 1]
            prev_step = {"label": prev["label"], "url": prev["url"]}
        if current_index + 1 < len(cells) and cells[current_index + 1]["id"] is not None:
            nxt = cells[current_index + 1]
            next_step = {"label": nxt["label"], "url": nxt["url"]}

    done = sum(1 for c in cells if c["done"])
    total = len(cells)
    return {
        "cells": cells,
        "done": done,
        "total": total,
        "percent": round(done * 100 / total) if total else 0,
        "next": pending,
        "prev_step": prev_step,
        "next_step": next_step,
        "complete": total > 0 and done == total,
        "runtime": project_runtime(project, get_profile(profile_id)),
    }


def get_or_create_research(project_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM research WHERE project_id=?", (project_id,)).fetchone()
        if row:
            return dict(row)
        conn.execute(
            "INSERT INTO research (project_id, updated_at) VALUES (?, ?)", (project_id, now_iso())
        )
        row = conn.execute("SELECT * FROM research WHERE project_id=?", (project_id,)).fetchone()
        return dict(row) if row else {"project_id": project_id}


def get_or_create_concept(project_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM concept WHERE project_id=?", (project_id,)).fetchone()
        if row:
            return dict(row)
        conn.execute(
            "INSERT INTO concept (project_id, updated_at) VALUES (?, ?)", (project_id, now_iso())
        )
        row = conn.execute("SELECT * FROM concept WHERE project_id=?", (project_id,)).fetchone()
        return dict(row) if row else {"project_id": project_id}


def _ensure_project_videos(conn, project_id, seed_defaults=False):
    if not conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
        return []
    now = now_iso()
    next_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM videos WHERE project_id=?",
        (project_id,),
    ).fetchone()["n"]
    defaults = (
        ("long", "Video 5 min", "long", "16:9 horizontal"),
        ("short", "Video 1 min", "short", "9:16 vertical"),
    )
    if seed_defaults:
        for key, name, script_type, video_format in defaults:
            conn.execute(
                """
                INSERT OR IGNORE INTO videos
                    (project_id, key, name, script_type, format, sort_order, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    project_id,
                    key,
                    name,
                    script_type,
                    video_format,
                    next_order,
                    now,
                    now,
                ),
            )
            next_order += 1
    for script in conn.execute(
        "SELECT id, project_id, type, video_id FROM scripts WHERE project_id=? AND video_id IS NULL",
        (project_id,),
    ).fetchall():
        video = conn.execute(
            "SELECT id FROM videos WHERE project_id=? AND key=?",
            (project_id, script["type"]),
        ).fetchone()
        if video:
            conn.execute("UPDATE scripts SET video_id=? WHERE id=?", (video["id"], script["id"]))
    metadata_keys = {
        "youtube_long": "long",
        "facebook_long": "long",
        "youtube_short": "short",
        "reels_short": "short",
    }
    for record in conn.execute(
        "SELECT id, project_id, platform, video_id FROM metadata_records "
        "WHERE project_id=? AND video_id IS NULL",
        (project_id,),
    ).fetchall():
        key = metadata_keys.get(record["platform"])
        video = conn.execute(
            "SELECT id FROM videos WHERE project_id=? AND key=?",
            (project_id, key),
        ).fetchone() if key else None
        if video:
            conn.execute("UPDATE metadata_records SET video_id=? WHERE id=?", (video["id"], record["id"]))
    for record in conn.execute(
        "SELECT id, project_id, script_type, video_id FROM thumbnail_records "
        "WHERE project_id=? AND video_id IS NULL",
        (project_id,),
    ).fetchall():
        video = conn.execute(
            "SELECT id FROM videos WHERE project_id=? AND key=?",
            (project_id, record["script_type"]),
        ).fetchone()
        if video:
            conn.execute("UPDATE thumbnail_records SET video_id=? WHERE id=?", (video["id"], record["id"]))
    return load_project_videos(project_id, conn)


def ensure_project_videos(project_id):
    with get_db() as conn:
        return _ensure_project_videos(conn, project_id, seed_defaults=False)


def ensure_default_project_videos(project_id):
    with get_db() as conn:
        return _ensure_project_videos(conn, project_id, seed_defaults=True)


def load_project_videos(project_id, conn=None):
    if conn is None:
        with get_db() as own_conn:
            return load_project_videos(project_id, own_conn)
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM videos WHERE project_id=? ORDER BY sort_order, id",
            (project_id,),
        ).fetchall()
    ]


def get_project_video(project_id, video_id, conn=None):
    if conn is None:
        with get_db() as own_conn:
            return get_project_video(project_id, video_id, own_conn)
    row = conn.execute(
        "SELECT * FROM videos WHERE project_id=? AND id=?",
        (project_id, video_id),
    ).fetchone()
    return dict(row) if row else None


def create_project_video(project_id, name, script_type="short", conn=None):
    if conn is None:
        with get_db() as own_conn:
            return create_project_video(project_id, name, script_type, own_conn)
    clean_name = (name or "").strip() or "Nuevo video"
    script_type = script_type if script_type in ("long", "short") else "short"
    now = now_iso()
    next_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM videos WHERE project_id=?",
        (project_id,),
    ).fetchone()["n"]
    cursor = conn.execute(
        """
        INSERT INTO videos
            (project_id, key, name, script_type, format, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            project_id,
            f"video_{next_order + 1}",
            clean_name,
            script_type,
            "16:9 horizontal" if script_type == "long" else "9:16 vertical",
            next_order,
            now,
            now,
        ),
    )
    row = conn.execute("SELECT * FROM videos WHERE id=?", (cursor.lastrowid,)).fetchone()
    return dict(row) if row else None


def delete_project_video(project_id, video_id, conn=None):
    if conn is None:
        with get_db() as own_conn:
            return delete_project_video(project_id, video_id, own_conn)
    cur = conn.execute(
        "DELETE FROM videos WHERE project_id=? AND id=?",
        (project_id, video_id),
    )
    return cur.rowcount > 0


def get_script_for_video(project_id, video_id, conn=None):
    if conn is None:
        with get_db() as own_conn:
            return get_script_for_video(project_id, video_id, own_conn)
    row = conn.execute(
        "SELECT * FROM scripts WHERE project_id=? AND video_id=?",
        (project_id, video_id),
    ).fetchone()
    return dict(row) if row else None


def script_prompt_type(conn, script):
    video_id = script.get("video_id")
    if video_id is not None:
        video = conn.execute(
            "SELECT script_type FROM videos WHERE id=?", (video_id,)
        ).fetchone()
        if video:
            return video["script_type"]
    return script.get("type") if script.get("type") in ("long", "short") else "short"


def get_script(project_id, script_type):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT s.*
            FROM scripts s
            LEFT JOIN videos v ON v.id=s.video_id
            WHERE s.project_id=?
              AND (v.key=? OR (v.id IS NULL AND s.type=?))
            ORDER BY v.sort_order, s.id
            LIMIT 1
            """,
            (project_id, script_type, script_type),
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
    """Construye el prompt para la fase de concepto, anclado en la investigación.

    ``research`` es el dict que devuelve ``parse_research`` con las claves
    ``content`` (RESUMEN), ``facts`` (HECHOS CONFIRMADOS + DATOS CLAVE),
    ``theories`` (TEORÍAS + CONTROVERSIAS), ``sources`` y ``unverified``.
    """
    sys_prompt = CONFIG["prompts"]["concept"]["system"]
    fmt = CONFIG["prompts"]["concept"]["format"]
    facts = research.get("facts") or []
    theories = research.get("theories") or []
    sources = research.get("sources") or []
    unverified = research.get("unverified") or []
    facts_block = "\n".join(f"- {f}" for f in facts[:12]) or "- (sin hechos registrados)"
    theories_block = "\n".join(f"- {t}" for t in theories[:8]) or "- (sin teorías registradas)"
    sources_block = "\n".join(f"- {s}" for s in sources[:8]) or "- (sin fuentes registradas)"
    unverified_block = (
        "\n".join(f"- {u}" for u in unverified[:6])
        if unverified
        else "- (ninguna marcada como dudosa)"
    )
    user_msg = (
        f"Tema: {project['topic']}\n\n"
        f"RESUMEN DE LA INVESTIGACIÓN:\n{research.get('content', '')[:2500]}\n\n"
        f"HECHOS CONFIRMADOS (úsalos como ancla de la tesis):\n{facts_block}\n\n"
        f"TEORÍAS Y VERSIONES:\n{theories_block}\n\n"
        f"FUENTES DISPONIBLES:\n{sources_block}\n\n"
        f"AFIRMACIONES QUE REQUIEREN VERIFICACIÓN (no las uses como base):\n{unverified_block}\n\n"
        f"Perfil del proyecto:\n"
        f"- Tono: {profile['tone'] if profile else 'serio'}\n"
        f"- Estilo: {profile['style'] if profile else 'cinematográfico'}\n"
        f"- Nivel de misterio: {profile['mystery_level'] if profile else 7}/10\n"
        f"- Nivel de dramatización: {profile['drama_level'] if profile else 6}/10\n\n"
        f"Genera un concepto potente anclado en los hechos confirmados y devuelve SIEMPRE en este formato:\n\n{fmt}"
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
        except Exception as e:
            # expected: key_points puede venir como string ya formateado;
            # el json.loads falla y caemos al string original.
            log.debug("key_points no es JSON, se usa como string: %s", e)

    user_msg = (
        f"Tema: {project['topic']}\n"
        f"Duración objetivo: {duration_txt}\n"
        f"Ángulo: {concept.get('angle', '')}\n"
        f"Tesis: {concept.get('thesis', '')}\n"
        f"Puntos clave:\n{key_points or ''}\n\n"
        f"Datos de la investigación:\n{research.get('content', '')[:2500]}\n\n"
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
        f"Duración total objetivo: {script.get('word_count', 0) / (profile['narration_speed'] if profile else 150) * 60:.0f} segundos\n\n"
        f"Guion a convertir en escenas:\n{script.get('body_full', '')}\n\n"
        f"Devuelve SOLO el JSON con las escenas, en este formato:\n\n{fmt}"
    )
    return sys_prompt, user_msg


def build_metadata_prompt(project, profile, script, platform):
    """Resuelve (system, format) para la plataforma pedida.

    Las plataformas válidas son ``youtube_long``, ``facebook_long``,
    ``youtube_short`` y ``reels_short``. Cualquier otro valor cae a
    ``youtube_long`` como fallback silencioso.
    """
    key = f"metadata_{platform}"
    cfg = CONFIG["prompts"].get(key) or CONFIG["prompts"].get("metadata_youtube_long")
    if not cfg:
        log.warning("[build_metadata_prompt] platform '%s' no tiene prompt en CONFIG", platform)
        return "", ""
    sys_prompt = cfg["system"]
    fmt = cfg["format"]
    platforms_raw = profile["platforms"] if profile else ""
    platforms_list = []
    if platforms_raw:
        try:
            platforms_list = json.loads(platforms_raw)
        except Exception as e:
            # expected: platforms puede ser un string legacy separado
            # por comas en vez de un JSON array; caemos a lista de uno.
            log.debug("platforms no es JSON, se trata como string: %s", e)
            platforms_list = [platforms_raw]
    platforms_txt = ", ".join(platforms_list) if platforms_list else "no definidas"
    user_msg = (
        f"Tema: {project['topic']}\n"
        f"Título del guion: {script.get('title', '')}\n"
        f"Hook: {script.get('hook', '')}\n"
        f"Tipo de contenido: {profile['content_type'] if profile else ''}\n"
        f"Plataformas objetivo: {platforms_txt}\n\n"
        f"Guion completo:\n{script.get('body_full', '')[:3000]}\n\n"
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
        f"Título del guion: {script.get('title', '')}\n"
        f"Hook: {script.get('hook', '')}\n"
        f"Tipo de contenido: {profile['content_type'] if profile else 'documental'}\n"
        f"Estilo visual: {profile['style'] if profile else 'cinematográfico'}\n"
        f"Nivel de misterio: {profile['mystery_level'] if profile else 7}/10\n\n"
        f"Ángulo y tesis del guion:\n{script.get('body_full', '')[:2500]}\n\n"
        f"Devuelve SIEMPRE en este formato:\n\n{fmt}"
    )
    return sys_prompt, user_msg


def build_refiner_prompt(profile, stage_label, current_output, issues, original_format):
    """Construye el prompt del nodo ``refiner``.

    Args:
        profile: dict con el perfil activo (o None).
        stage_label: nombre lógico de la etapa (p.ej. "scripts").
        current_output: el output existente de la etapa (texto tal cual).
        issues: lista de tuplas ``(stage, severity, message, field, video_id)``.
        original_format: el bloque ``format`` del prompt original de la etapa,
            para que el refiner respete la estructura de salida.

    Returns:
        Tupla ``(sys_prompt, user_msg)``.
    """
    if not CONFIG.get("prompts", {}).get("refiner"):
        return "", ""
    sys_prompt = CONFIG["prompts"]["refiner"]["system"]
    fmt = CONFIG["prompts"]["refiner"]["format"]

    issue_lines: list[str] = []
    for stage, severity, message, field, video_id in issues:
        stage_str = stage or "?"
        video_str = f" video={video_id}" if video_id is not None else ""
        field_str = f" [{field}]" if field else ""
        issue_lines.append(f"- [{severity}] {stage_str}{video_str}{field_str}: {message}")
    issues_block = "\n".join(issue_lines) if issue_lines else "- (sin issues reportados)"

    safe_output = (current_output or "")[:8000]
    user_msg = (
        f"Etapa a refinar: {stage_label}\n\n"
        f"OUTPUT ACTUAL:\n```\n{safe_output}\n```\n\n"
        f"ISSUES REPORTADOS POR QC:\n{issues_block}\n\n"
        f"FORMATO DE SALIDA QUE DEBE RESPETAR EL OUTPUT REFINADO (mismo que el prompt original de la etapa):\n\n"
        f"```\n{(original_format or '').strip()}\n```\n\n"
        f"Devuelve tu respuesta en este formato:\n\n{fmt}"
    )
    return sys_prompt, user_msg


# ---------------------------------------------------------------------------
# Parsers, LLM y QC: extraídos a services/ (T2.1). Las definiciones
# viven en services/parsers.py, services/llm.py y services/qc.py; este
# modulo solo los re-exporta para preservar la API interna.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------


@app.route("/")
def dashboard():
    with get_db() as conn:
        projects = [
            dict(r)
            for r in conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        ]
        profiles = [
            dict(r) for r in conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()
        ]
    for p in projects:
        p["stages"] = project_stage_status(p)
    return render_template("dashboard.html", projects=projects, profiles=profiles, config=CONFIG)


@app.route("/projects/new", methods=["GET", "POST"])
def new_project():
    with get_db() as conn:
        profiles = [
            dict(r) for r in conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()
        ]
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        topic = request.form.get("topic", "").strip()
        profile_id = request.form.get("profile_id") or None
        if not name or not topic:
            flash("Nombre y tema son obligatorios", "error")
            return render_template("new_project.html", profiles=profiles)
        if profile_id is None:
            default_profile = get_default_profile()
            if default_profile:
                profile_id = default_profile["id"]
        with get_db() as conn:
            cur = conn.execute(
                """
                INSERT INTO projects (name, topic, profile_id, status, created_at, updated_at)
                VALUES (?, ?, ?, 'research', ?, ?)
            """,
                (name, topic, profile_id, now_iso(), now_iso()),
            )
            new_id = cur.lastrowid
        assert new_id is not None
        ensure_default_project_videos(new_id)
        try:
            sync_project_stages_for_project(new_id)
        except Exception:
            log.exception("[sync_project_stages_for_project] %s", new_id)
        try:
            sync_project_folder(new_id)
        except Exception:
            log.exception("[sync_project_folder] create project %s", new_id)
        return redirect(url_for("view_project", project_id=new_id))
    return render_template(
        "new_project.html", profiles=profiles, default_profile=get_default_profile()
    )


@app.route("/projects/<int:project_id>")
def view_project(project_id):
    with get_db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            abort(404)
        project = dict(project)
        profile = get_profile(project["profile_id"])
        videos = load_project_videos(project_id, conn)
    project["stages"] = project_stage_status(project)
    saved_prompts = list_profile_prompts(project["profile_id"])
    return render_template(
        "project.html",
        project=project,
        profile=profile,
        saved_prompts=saved_prompts,
        videos=videos,
    )


@app.route("/projects/<int:project_id>/videos", methods=["POST"])
def manage_project_videos(project_id):
    with get_db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            abort(404)
        action = request.form.get("action")
        if action == "add":
            video = create_project_video(
                project_id,
                request.form.get("name", ""),
                request.form.get("script_type", "short"),
                conn,
            )
            if video:
                conn.execute(
                    "UPDATE projects SET updated_at=? WHERE id=?",
                    (now_iso(), project_id),
                )
                flash(f"Video «{video['name']}» añadido", "ok")
            else:
                flash("No se pudo añadir el video", "error")
        elif action == "delete":
            video_id = request.form.get("video_id")
            video = get_project_video(project_id, video_id, conn)
            deleted = delete_project_video(project_id, video_id, conn)
            if deleted:
                conn.execute(
                    "UPDATE projects SET updated_at=? WHERE id=?",
                    (now_iso(), project_id),
                )
                flash(f"Video «{video['name'] if video else ''}» eliminado", "ok")
            else:
                flash("No se encontró el video", "error")
        else:
            flash("Acción no válida", "error")
    try:
        sync_project_folder(project_id)
    except Exception:
        log.exception("[sync_project_folder] videos %s", project_id)
    return redirect(url_for("view_project", project_id=project_id))


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
def delete_project(project_id):
    with get_db() as conn:
        row = conn.execute("SELECT name FROM projects WHERE id=?", (project_id,)).fetchone()
        name = row["name"] if row else None
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    if name:
        try:
            delete_project_folder(project_id, name)
        except Exception:
            log.exception("[delete_project_folder] %s", project_id)
    flash("Proyecto eliminado", "ok")
    return redirect(url_for("dashboard"))


@app.route("/projects/<int:project_id>/stages/<int:stage_id>", methods=["GET", "POST"])
def project_stage(project_id, stage_id):
    """Ruta genérica de etapa. Sustituye a las páginas individuales de cada fase."""
    project = fetch_project_or_404(project_id)
    sync_project_stages_for_project(project_id)
    stages = load_project_stages(project_id)
    current = next((s for s in stages if s["id"] == stage_id), None)
    if not current:
        abort(404)
    if not current.get("is_active"):
        flash("Esta etapa está desactivada en el perfil", "error")
        return redirect(url_for("view_project", project_id=project_id))
    profile = get_profile(project["profile_id"])

    label = ROADMAP_STAGE_LABELS.get(current["stage_name"], current["stage_name"])
    stage_view = {
        "id": current["id"],
        "key": current["stage_name"],
        "name": label,
        "num": f"{current['sort_order'] + 1:02d}",
        "instruction": current.get("instruction") or "",
        "description": "",
    }
    project_stage_view = {
        "id": current["id"],
        "instruction": current.get("instruction") or "",
        "response": current.get("response") or "",
        "updated_at": current.get("updated_at") or "",
    }
    stage_links = [
        {
            "id": s["id"],
            "key": s["stage_name"],
            "name": ROADMAP_STAGE_LABELS.get(s["stage_name"], s["stage_name"]),
            "num": f"{s['sort_order'] + 1:02d}",
            "done": bool((s.get("response") or "").strip()),
            "complete": bool((s.get("response") or "").strip()),
        }
        for s in stages
        if s.get("is_active")
    ]

    if request.method == "POST":
        action = request.form.get("action")
        if action == "generate":
            sys_p, raw, user_msg = generate_stage_response(project_id, stage_id)
            return render_template(
                "stage.html",
                project=project,
                profile=profile,
                stage=stage_view,
                project_stage=dict(
                    project_stage_view,
                    instruction=request.form.get("instruction", project_stage_view["instruction"]),
                ),
                stages=stage_links,
                generated=raw,
                sys_prompt=sys_p,
                user_prompt=user_msg,
                current_stage=stage_id,
            )
        if action == "save":
            response_text = request.form.get("response", "").strip()
            instruction_text = (request.form.get("instruction") or "").strip()
            now = now_iso()
            with get_db() as conn:
                if instruction_text:
                    conn.execute(
                        "UPDATE project_stages SET response=?, instruction=?, updated_at=? "
                        "WHERE id=? AND project_id=?",
                        (response_text, instruction_text, now, stage_id, project_id),
                    )
                else:
                    conn.execute(
                        "UPDATE project_stages SET response=?, updated_at=? "
                        "WHERE id=? AND project_id=?",
                        (response_text, now, stage_id, project_id),
                    )
                conn.execute(
                    "UPDATE projects SET updated_at=? WHERE id=?",
                    (now, project_id),
                )
                recompute_project_status(conn, project_id)
            try:
                sync_project_folder(project_id)
            except Exception:
                log.exception("[sync_project_folder] project_stage %s/%s", project_id, stage_id)
            flash("Etapa guardada", "ok")
            return redirect(
                url_for("project_stage", project_id=project_id, stage_id=stage_id)
            )

    return render_template(
        "stage.html",
        project=project,
        profile=profile,
        stage=stage_view,
        project_stage=project_stage_view,
        stages=stage_links,
        current_stage=stage_id,
    )


# --- Investigación -----------------------------------------------------------


@app.route("/projects/<int:project_id>/research", methods=["GET", "POST"])
def research(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
    research_obj = get_or_create_research(project_id)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "generate_prompt":
            sys_p, user_p = build_research_prompt(project, profile)
            save_profile_prompt(project["profile_id"], "research", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template(
                "research.html",
                project=project,
                profile=profile,
                research=research_obj,
                generated=generated,
                sys_prompt=sys_p,
                user_prompt=user_p,
            )
        elif action == "save":
            text = request.form.get("content", "").strip()
            if text:
                parsed = parse_research(text)
                with get_db() as conn:
                    conn.execute(
                        """
                        UPDATE research SET content=?, sources=?, facts=?,
                            theories=?, unverified=?, updated_at=?
                        WHERE project_id=?
                    """,
                        (
                            parsed["content"] or text,
                            json.dumps(parsed["sources"], ensure_ascii=False),
                            json.dumps(parsed["facts"], ensure_ascii=False),
                            json.dumps(parsed["theories"], ensure_ascii=False),
                            json.dumps(parsed["unverified"], ensure_ascii=False),
                            now_iso(),
                            project_id,
                        ),
                    )
                    conn.execute(
                        "UPDATE projects SET updated_at=? WHERE id=?", (now_iso(), project_id)
                    )
                flash("Investigación guardada", "ok")
            try:
                sync_project_folder(project_id)
            except Exception:
                log.exception("[sync_project_folder] research %s", project_id)
            return redirect(url_for("research", project_id=project_id))

    sources = json.loads(research_obj.get("sources") or "[]")
    facts = json.loads(research_obj.get("facts") or "[]")
    return render_template(
        "research.html",
        project=project,
        profile=profile,
        research=research_obj,
        sources=sources,
        facts=facts,
    )


# --- Concepto ----------------------------------------------------------------


@app.route("/projects/<int:project_id>/concept", methods=["GET", "POST"])
def concept(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        research_obj = fetch_optional_dict(
            conn, "SELECT * FROM research WHERE project_id=?", (project_id,)
        )
    concept_obj = get_or_create_concept(project_id)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "generate_prompt":
            if not research_obj or not research_obj.get("content"):
                flash("Necesitas tener investigación antes de generar el concepto", "error")
                return redirect(url_for("research", project_id=project_id))
            sys_p, user_p = build_concept_prompt(project, profile, research_obj)
            save_profile_prompt(project["profile_id"], "concept", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template(
                "concept.html",
                project=project,
                profile=profile,
                concept=concept_obj,
                generated=generated,
                sys_prompt=sys_p,
                user_prompt=user_p,
            )
        elif action == "save":
            text = request.form.get("text", "").strip()
            if text:
                parsed = parse_concept(text)
                with get_db() as conn:
                    conn.execute(
                        """
                        UPDATE concept SET angle=?, thesis=?, key_points=?,
                            emotional_hook=?, what_they_learn=?, what_they_feel=?,
                            risks=?, updated_at=? WHERE project_id=?
                    """,
                        (
                            parsed["angle"],
                            parsed["thesis"],
                            json.dumps(parsed["key_points"], ensure_ascii=False),
                            parsed["emotional_hook"],
                            json.dumps(parsed["what_they_learn"], ensure_ascii=False),
                            json.dumps(parsed["what_they_feel"], ensure_ascii=False),
                            json.dumps(parsed["risks"], ensure_ascii=False),
                            now_iso(),
                            project_id,
                        ),
                    )
                    conn.execute(
                        "UPDATE projects SET status='concept', updated_at=? WHERE id=?",
                        (now_iso(), project_id),
                    )
                flash("Concepto guardado", "ok")
            try:
                sync_project_folder(project_id)
            except Exception:
                log.exception("[sync_project_folder] concept %s", project_id)
            return redirect(url_for("concept", project_id=project_id))

    key_points = json.loads(concept_obj.get("key_points") or "[]")
    return render_template(
        "concept.html", project=project, profile=profile, concept=concept_obj, key_points=key_points
    )


# --- Guiones -----------------------------------------------------------------


@app.route("/projects/<int:project_id>/scripts", methods=["GET", "POST"])
def scripts(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        videos = load_project_videos(project_id, conn)
        research_obj = fetch_optional_dict(
            conn, "SELECT * FROM research WHERE project_id=?", (project_id,)
        )
        concept_obj = fetch_optional_dict(
            conn, "SELECT * FROM concept WHERE project_id=?", (project_id,)
        )
        scripts_by_video = {
            row["video_id"]: dict(row)
            for row in conn.execute(
                "SELECT * FROM scripts WHERE project_id=? AND video_id IS NOT NULL",
                (project_id,),
            ).fetchall()
        }

    if request.method == "POST":
        action = request.form.get("action")
        video_id = request.form.get("video_id")
        video = next((v for v in videos if str(v["id"]) == str(video_id)), None) if video_id else None
        if video is None:
            legacy_type = request.form.get("script_type", "long")
            video = next((v for v in videos if v["key"] == legacy_type), videos[0] if videos else None)
        if video is None:
            flash("Selecciona un video", "error")
            return redirect(url_for("scripts", project_id=project_id))
        stype = video["script_type"]

        if action == "generate_prompt":
            if not concept_obj or not concept_obj.get("angle"):
                flash("Necesitas un concepto antes de generar el guion", "error")
                return redirect(url_for("concept", project_id=project_id))
            sys_p, user_p = build_script_prompt(project, profile, research_obj, concept_obj, stype)
            save_profile_prompt(project["profile_id"], f"script_{stype}", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template(
                "scripts.html",
                project=project,
                profile=profile,
                videos=videos,
                scripts_by_video=scripts_by_video,
                profile_prompts=list_profile_prompts(project["profile_id"]),
                generated=generated,
                gen_video_id=video["id"],
                gen_type=stype,
                sys_prompt=sys_p,
                user_prompt=user_p,
            )
        elif action == "save":
            text = request.form.get("text", "").strip()
            if text:
                parsed = parse_script(text, stype)
                wc = count_words(parsed["body_full"] or text)
                with get_db() as conn:
                    existing = get_script_for_video(project_id, video["id"], conn)
                    values = (
                        parsed["title"],
                        parsed["hook"],
                        parsed["context"],
                        parsed["development"],
                        parsed["revelations"],
                        parsed["conclusion"],
                        parsed["cta"],
                        parsed["body_full"],
                        wc,
                        now_iso(),
                    )
                    if existing:
                        conn.execute(
                            """
                            UPDATE scripts SET title=?, hook=?, context=?, development=?,
                                revelations=?, conclusion=?, cta=?, body_full=?,
                                word_count=?, updated_at=?, video_id=? WHERE id=?
                        """,
                            (*values, video["id"], existing["id"]),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO scripts (project_id, video_id, type, title, hook, context,
                                development, revelations, conclusion, cta, body_full,
                                word_count, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                project_id,
                                video["id"],
                                video["key"],
                                *values,
                            ),
                        )
                    conn.execute(
                        "UPDATE projects SET status='scripts', updated_at=? WHERE id=?",
                        (now_iso(), project_id),
                    )
                flash(f"Guion «{video['name']}» guardado", "ok")
            try:
                sync_project_folder(project_id)
            except Exception:
                log.exception("[sync_project_folder] scripts %s", project_id)
            return redirect(url_for("scripts", project_id=project_id, video_id=video["id"]))

    return render_template(
        "scripts.html",
        project=project,
        profile=profile,
        videos=videos,
        scripts_by_video=scripts_by_video,
        profile_prompts=list_profile_prompts(project["profile_id"]),
    )


# --- Escenas -----------------------------------------------------------------


@app.route("/projects/<int:project_id>/scenes", methods=["GET", "POST"])
def scenes(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        videos = load_project_videos(project_id, conn)
        scripts_by_video = {
            row["video_id"]: dict(row)
            for row in conn.execute(
                "SELECT * FROM scripts WHERE project_id=? AND video_id IS NOT NULL",
                (project_id,),
            ).fetchall()
        }

    def default_video():
        for key in ("long", "short"):
            video = next((v for v in videos if v["key"] == key), None)
            if video and video["id"] in scripts_by_video:
                return video
        video = next((v for v in videos if v["id"] in scripts_by_video), None)
        return video or (videos[0] if videos else None)

    raw_video_id = request.values.get("video_id")
    if not raw_video_id:
        raw_script_id = request.values.get("script_id")
        if raw_script_id:
            matching = next(
                (s for s in scripts_by_video.values() if str(s["id"]) == str(raw_script_id)),
                None,
            )
            raw_video_id = matching["video_id"] if matching else None
    active_video = next(
        (v for v in videos if str(v["id"]) == str(raw_video_id)), None
    ) or default_video()
    active_script = scripts_by_video.get(active_video["id"]) if active_video else None
    active_script_id = active_script["id"] if active_script else None
    scenes_rows = []
    if active_script_id is not None:
        with get_db() as conn:
            scenes_rows = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM scenes WHERE project_id=? AND script_id=? ORDER BY scene_number",
                    (project_id, active_script_id),
                ).fetchall()
            ]

    if request.method == "POST":
        action = request.form.get("action")
        video_id = request.form.get("video_id")
        if not video_id and request.form.get("script_id"):
            script = next(
                (s for s in scripts_by_video.values() if str(s["id"]) == str(request.form["script_id"])),
                None,
            )
            video_id = script["video_id"] if script else None
        video = next((v for v in videos if str(v["id"]) == str(video_id)), None) or active_video
        script = scripts_by_video.get(video["id"]) if video else None
        if not video or not script:
            flash("Selecciona un guion", "error")
            return redirect(url_for("scenes", project_id=project_id))

        if action == "generate_prompt":
            sys_p, user_p = build_scenes_prompt(project, profile, script)
            save_profile_prompt(project["profile_id"], "scenes", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template(
                "scenes.html",
                project=project,
                profile=profile,
                videos=videos,
                scripts_by_video=scripts_by_video,
                scenes=scenes_rows,
                generated=generated,
                saved_prompt=list_profile_prompts(project["profile_id"]).get("scenes"),
                gen_video_id=video["id"],
                active_video_id=video["id"],
                active_script_id=script["id"],
                sys_prompt=sys_p,
                user_prompt=user_p,
            )
        elif action == "save":
            text = request.form.get("text", "").strip()
            if text:
                parsed = parse_scenes(text)
                if not parsed:
                    flash(
                        "No se pudo extraer escenas de la respuesta (¿formato TST correcto?)",
                        "error",
                    )
                    return redirect(url_for("scenes", project_id=project_id, video_id=video["id"]))
                wpm = (profile.get("narration_speed") if profile else None) or 150
                total_words = sum(count_words(sc.get("narration_segment", "")) for sc in parsed)
                for scene in parsed:
                    if not scene.get("duration_seconds") and total_words > 0:
                        words = count_words(scene.get("narration_segment", ""))
                        scene["duration_seconds"] = max(1, round(words / wpm * 60))
                with get_db() as conn:
                    conn.execute(
                        "DELETE FROM scenes WHERE project_id=? AND script_id=?",
                        (project_id, script["id"]),
                    )
                    for scene in parsed:
                        try:
                            scene_num = int(scene.get("scene_number", 0))
                        except (TypeError, ValueError) as e:
                            log.debug("scene_number no numerico: %s", e)
                            scene_num = 0
                        try:
                            duration = int(scene.get("duration_seconds", 0))
                        except (TypeError, ValueError) as e:
                            log.debug("duration_seconds no numerico: %s", e)
                            duration = 0
                        image_prompt = scene.get("image_prompt") or scene.get("visual_description") or ""
                        conn.execute(
                            """
                            INSERT INTO scenes (project_id, script_id, scene_number,
                                narration, visual_description, camera_movement,
                                transition, duration_seconds, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                project_id,
                                script["id"],
                                scene_num,
                                scene.get("narration_segment", ""),
                                image_prompt,
                                scene.get("camera_movement", "") or "",
                                scene.get("transition", "") or "",
                                duration,
                                now_iso(),
                            ),
                        )
                    conn.execute(
                        "UPDATE projects SET status='scenes', updated_at=? WHERE id=?",
                        (now_iso(), project_id),
                    )
                flash(f"Guardadas {len(parsed)} escenas de {video['name']}", "ok")
            try:
                sync_project_folder(project_id)
            except Exception:
                log.exception("[sync_project_folder] scenes %s", project_id)
            return redirect(url_for("scenes", project_id=project_id, video_id=video["id"]))
        elif action == "delete":
            scene_id = request.form.get("scene_id")
            with get_db() as conn:
                conn.execute(
                    "DELETE FROM scenes WHERE id=? AND project_id=? AND script_id=?",
                    (scene_id, project_id, script["id"]),
                )
            return redirect(url_for("scenes", project_id=project_id, video_id=video["id"]))

    return render_template(
        "scenes.html",
        project=project,
        profile=profile,
        videos=videos,
        scripts_by_video=scripts_by_video,
        scenes=scenes_rows,
        saved_prompt=list_profile_prompts(project["profile_id"]).get("scenes"),
        generated="",
        sys_prompt="",
        user_prompt="",
        gen_video_id=None,
        active_video_id=active_video["id"] if active_video else None,
        active_script_id=active_script_id,
    )


# --- Prompts -----------------------------------------------------------------

# --- Metadata ----------------------------------------------------------------


@app.route("/projects/<int:project_id>/metadata", methods=["GET", "POST"])
def metadata(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        videos = load_project_videos(project_id, conn)
        scripts_by_video = {
            row["video_id"]: dict(row)
            for row in conn.execute(
                "SELECT * FROM scripts WHERE project_id=? AND video_id IS NOT NULL",
                (project_id,),
            ).fetchall()
        }
        scripts_by_id = {
            script["id"]: script
            for script in scripts_by_video.values()
        }
        meta_rows = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM metadata_records WHERE project_id=?", (project_id,)
            ).fetchall()
        ]

    metadata_platforms = {
        "long": ("youtube_long", "facebook_long"),
        "short": ("youtube_short", "reels_short"),
    }
    platform_by_video = {
        video["id"]: metadata_platforms.get(video["script_type"], metadata_platforms["long"])
        for video in videos
    }
    metadata_by_video: dict[int, dict[str, dict]] = {
        video["id"]: {} for video in videos
    }
    for record in meta_rows:
        video_id = record.get("video_id")
        if video_id in metadata_by_video:
            metadata_by_video[video_id][record["platform"]] = record
            continue
        for video in videos:
            if record.get("platform") in platform_by_video[video["id"]]:
                metadata_by_video[video["id"]][record["platform"]] = record
                break
    for platform_map in metadata_by_video.values():
        for record in platform_map.values():
            record["titles_list"] = json.loads(record.get("titles") or "[]")
            record["chapters_list"] = json.loads(record.get("chapters") or "[]")
            record["tags_list"] = json.loads(record.get("tags") or "[]")
            record["hashtags_list"] = json.loads(record.get("hashtags") or "[]")
            record["on_screen_list"] = json.loads(record.get("on_screen_text") or "[]")

    saved_prompts = list_profile_prompts(project["profile_id"])

    if request.method == "POST":
        action = request.form.get("action")
        video_id = request.form.get("video_id")
        platform = request.form.get("platform")
        video = next((v for v in videos if str(v["id"]) == str(video_id)), None)
        if not video and platform:
            fallback_key = "long" if "long" in platform else "short" if "short" in platform else None
            video = next((v for v in videos if v["key"] == fallback_key), None)
        if not video and platform:
            fallback_key = "long" if "long" in platform else "short" if "short" in platform else None
            video = {
                "id": None,
                "key": fallback_key or "long",
                "name": "Video 5 min" if fallback_key == "long" else "Video 1 min",
                "script_type": fallback_key or "long",
            }
        if not video:
            flash("Selecciona un video", "error")
            return redirect(url_for("metadata", project_id=project_id))
        available_platforms = platform_by_video.get(video["id"])
        if available_platforms is None:
            available_platforms = platform_by_video.get(video["script_type"], ("youtube_long", "facebook_long"))
            platform_by_video[video["id"]] = available_platforms
        if platform not in available_platforms:
            platform = available_platforms[0]
        requested_script = request.form.get("script_id")
        script = (
            scripts_by_id.get(int(requested_script))
            if requested_script and requested_script.isdigit()
            else None
        ) or scripts_by_video.get(video["id"])
        if action == "generate_prompt":
            if not script:
                flash("Selecciona un guion", "error")
                return redirect(url_for("metadata", project_id=project_id, video_id=video["id"]))
            sys_p, user_p = build_metadata_prompt(project, profile, script, platform)
            prompt_key = (
                f"metadata_{platform}"
                if video["key"] in ("long", "short")
                else f"metadata_{platform}_{video['id']}"
            )
            save_profile_prompt(project["profile_id"], prompt_key, sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template(
                "metadata.html",
                project=project,
                profile=profile,
                videos=videos,
                scripts_by_video=scripts_by_video,
                metadata_by_video=metadata_by_video,
                metadata_platforms=platform_by_video,
                saved_prompts=saved_prompts,
                generated=generated,
                gen_video_id=video["id"],
                gen_platform=platform,
                gen_script_id=script["id"],
                sys_prompt=sys_p,
                user_prompt=user_p,
            )
        if action == "save":
            text = request.form.get("text", "").strip()
            if text:
                parsed = parse_metadata(text, platform)
                with get_db() as conn:
                    existing = conn.execute(
                        "SELECT id FROM metadata_records WHERE project_id=? AND video_id=? AND platform=?",
                        (project_id, video["id"], platform),
                    ).fetchone()
                    fields = (
                        json.dumps(parsed["titles"], ensure_ascii=False),
                        parsed["description"],
                        json.dumps(parsed["chapters"], ensure_ascii=False),
                        json.dumps(parsed["tags"], ensure_ascii=False),
                        json.dumps(parsed["hashtags"], ensure_ascii=False),
                        parsed["caption"],
                        parsed["hook"],
                        parsed["cta"],
                        json.dumps(parsed["on_screen_text"], ensure_ascii=False),
                    )
                    if existing:
                        conn.execute(
                            """
                            UPDATE metadata_records SET titles=?, description=?,
                                chapters=?, tags=?, hashtags=?, caption=?, hook=?, cta=?,
                                on_screen_text=?, video_id=?, updated_at=? WHERE id=?
                        """,
                            (*fields, video["id"], now_iso(), existing["id"]),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO metadata_records (project_id, video_id, platform,
                                titles, description, chapters, tags, hashtags, caption,
                                hook, cta, on_screen_text, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (project_id, video["id"], platform, *fields, now_iso()),
                        )
                    conn.execute(
                        "UPDATE projects SET status='metadata', updated_at=? WHERE id=?",
                        (now_iso(), project_id),
                    )
                flash(f"Metadata de {video['name']} guardada", "ok")
            try:
                sync_project_folder(project_id)
            except Exception:
                log.exception("[sync_project_folder] metadata %s", project_id)
            return redirect(url_for("metadata", project_id=project_id, video_id=video["id"]))

    return render_template(
        "metadata.html",
        project=project,
        profile=profile,
        videos=videos,
        scripts_by_video=scripts_by_video,
        metadata_by_video=metadata_by_video,
        metadata_platforms=platform_by_video,
        saved_prompts=saved_prompts,
    )


# --- Miniaturas --------------------------------------------------------------


@app.route("/projects/<int:project_id>/thumbnails", methods=["GET", "POST"])
def thumbnails(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        videos = load_project_videos(project_id, conn)
        scripts_by_video = {
            row["video_id"]: dict(row)
            for row in conn.execute(
                "SELECT * FROM scripts WHERE project_id=? AND video_id IS NOT NULL",
                (project_id,)
            ).fetchall()
        }
        scripts_by_id = {
            script["id"]: script
            for script in scripts_by_video.values()
        }
        thumb_rows = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM thumbnail_records WHERE project_id=?", (project_id,)
            ).fetchall()
        ]

    thumbnail_by_video = {
        video["id"]: next(
            (row for row in thumb_rows if row.get("video_id") == video["id"] or
             (row.get("video_id") is None and row.get("script_type") == video["key"])),
            None,
        )
        for video in videos
    }
    saved_prompts = list_profile_prompts(project["profile_id"])

    if request.method == "POST":
        action = request.form.get("action")
        video_id = request.form.get("video_id")
        video = next((v for v in videos if str(v["id"]) == str(video_id)), None)
        if not video:
            flash("Selecciona un video", "error")
            return redirect(url_for("thumbnails", project_id=project_id))
        requested_script = request.form.get("script_id")
        script = (
            scripts_by_id.get(int(requested_script))
            if requested_script and requested_script.isdigit()
            else None
        ) or scripts_by_video.get(video["id"])
        if not script:
            flash("Selecciona un guion", "error")
            return redirect(url_for("thumbnails", project_id=project_id, video_id=video["id"]))
        sys_p, user_p = build_thumbnail_prompt(project, profile, script, video["script_type"])
        prompt_key = (
            f"thumbnail_{video['script_type']}"
            if video["key"] in ("long", "short")
            else f"thumbnail_{video['script_type']}_{video['id']}"
        )
        save_profile_prompt(project["profile_id"], prompt_key, sys_p, user_p)
        if action == "generate_prompt":
            generated = call_llm(sys_p, user_p)
            return render_template(
                "thumbnails.html",
                project=project,
                profile=profile,
                videos=videos,
                scripts_by_video=scripts_by_video,
                thumbnail_by_video=thumbnail_by_video,
                saved_prompts=saved_prompts,
                generated=generated,
                gen_video_id=video["id"],
                active_video_id=video["id"],
                sys_prompt=sys_p,
                user_prompt=user_p,
            )
        if action == "save":
            text = request.form.get("text", "").strip()
            if text:
                parsed = parse_thumbnail(text, video["script_type"])
                prompt_text = parsed["prompt"].strip()
                if not prompt_text:
                    flash("No se pudo extraer la miniatura (¿formato correcto?)", "error")
                    return redirect(url_for("thumbnails", project_id=project_id, video_id=video["id"]))
                with get_db() as conn:
                    existing = conn.execute(
                        "SELECT id FROM thumbnail_records WHERE project_id=? AND video_id=?",
                        (project_id, video["id"]),
                    ).fetchone()
                    if existing:
                        conn.execute(
                            """
                            UPDATE thumbnail_records SET prompt=?, script_type=?, video_id=?, updated_at=?
                            WHERE id=?
                        """,
                            (prompt_text, video["key"], video["id"], now_iso(), existing["id"]),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO thumbnail_records
                            (project_id, video_id, script_type, prompt, updated_at)
                            VALUES (?, ?, ?, ?, ?)
                        """,
                            (project_id, video["id"], video["key"], prompt_text, now_iso()),
                        )
                    conn.execute(
                        "UPDATE projects SET status='thumbnails', updated_at=? WHERE id=?",
                        (now_iso(), project_id),
                    )
                flash(f"Miniatura de {video['name']} guardada", "ok")
                try:
                    sync_project_folder(project_id)
                except Exception:
                    log.exception("[sync_project_folder] thumbnails %s", project_id)
            return redirect(url_for("thumbnails", project_id=project_id, video_id=video["id"]))

    return render_template(
        "thumbnails.html",
        project=project,
        profile=profile,
        videos=videos,
        scripts_by_video=scripts_by_video,
        thumbnail_by_video=thumbnail_by_video,
        saved_prompts=saved_prompts,
    )


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
                conn.execute(
                    "UPDATE projects SET status='ready', qc_state='skipped', updated_at=? WHERE id=?",
                    (now_iso(), project_id),
                )
            flash("Análisis omitido: el proyecto se ha marcado como listo para exportar", "ok")
            return redirect(url_for("qc", project_id=project_id, skipped=1))
        issues = run_qc(project_id)
        save_qc_issues(project_id, issues)
        errors = [i for i in issues if i[1] == "error"]
        with get_db() as conn:
            if errors:
                conn.execute(
                    "UPDATE projects SET updated_at=?, qc_state='analyzed' WHERE id=?",
                    (now_iso(), project_id),
                )
            else:
                conn.execute(
                    "UPDATE projects SET status='ready', qc_state='analyzed', updated_at=? WHERE id=?",
                    (now_iso(), project_id),
                )
        flash(f"Análisis completado: {len(issues)} avisos", "ok")
        try:
            sync_project_folder(project_id)
        except Exception:
            log.exception("[sync_project_folder] qc %s", project_id)
        if not issues:
            return redirect(url_for("qc", project_id=project_id, clean=1))
        return redirect(url_for("qc", project_id=project_id))
    with get_db() as conn:
        issues = [
            dict(r)
            for r in conn.execute(
                """SELECT * FROM qc_issues WHERE project_id=?
               ORDER BY CASE severity
                            WHEN 'error' THEN 0
                            WHEN 'warning' THEN 1
                            ELSE 2
                        END, stage""",
                (project_id,),
            ).fetchall()
        ]
        last_run_row = conn.execute(
            "SELECT MAX(created_at) AS last FROM qc_issues WHERE project_id=?",
            (project_id,),
        ).fetchone()
        last_run = last_run_row["last"] if last_run_row else None
    return render_template("qc.html", project=project, issues=issues, last_run=last_run)


# --- Export / sincronización de carpeta ---------------------------------------
#
# Las funciones ``safe_project_dir``, ``delete_project_folder`` y
# ``sync_project_folder`` ahora viven en ``services/sync.py`` (extracción
# desde el monolito — siguiente paso tras services/qc.py y services/llm.py).
# Se re-exportan arriba (línea 46) para preservar la API pública y los
# callers en este módulo.


@app.route("/projects/<int:project_id>/export", methods=["GET", "POST"])
def export(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        research_obj = fetch_optional_dict(
            conn, "SELECT * FROM research WHERE project_id=?", (project_id,)
        )
        concept_obj = fetch_optional_dict(
            conn, "SELECT * FROM concept WHERE project_id=?", (project_id,)
        )
        scripts_rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM scripts WHERE project_id=?", (project_id,)
            ).fetchall()
        ]
        scenes_rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM scenes WHERE project_id=? ORDER BY scene_number", (project_id,)
            ).fetchall()
        ]
        meta_rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM metadata_records WHERE project_id=?", (project_id,)
            ).fetchall()
        ]
        thumb_rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM thumbnail_records WHERE project_id=?", (project_id,)
            ).fetchall()
        ]
        videos = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM videos WHERE project_id=? ORDER BY sort_order, id", (project_id,)
            ).fetchall()
        ]

    out_dir = safe_project_dir(project_id, project["name"])
    if request.method == "POST":
        action = request.form.get("action", "zip")
        if action == "resync":
            out_dir, written = sync_project_folder(project_id)
            flash(f"Carpeta re-sincronizada ({len(written)} archivos)", "ok")
            return redirect(url_for("export", project_id=project_id))

        # action=zip: regenera y descarga el ZIP
        out_dir, written = sync_project_folder(project_id)
        safe_name = out_dir.name
        zip_path = PROJECTS_DIR / f"{safe_name}.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(out_dir):
                for file in files:
                    full = Path(root) / file
                    arc = full.relative_to(out_dir.parent)
                    zf.write(full, arc)
        flash(f"ZIP descargado y guardado en {zip_path.name}", "ok")
        return send_file(zip_path, as_attachment=True, download_name=zip_path.name)

    # GET: sincroniza si la carpeta no existe todavía y muestra el estado
    if not out_dir.exists():
        out_dir, written = sync_project_folder(project_id)
    folder_files = sorted(
        p.name + ("/" if p.is_dir() else "") for p in out_dir.rglob("*") if p != out_dir
    )

    with get_db() as conn:
        qc_errors = conn.execute(
            "SELECT COUNT(*) AS n FROM qc_issues WHERE project_id=? AND severity='error'",
            (project_id,),
        ).fetchone()["n"]

    return render_template(
        "export.html",
        project=project,
        profile=profile,
        has_research=bool(research_obj.get("content")),
        has_concept=bool(concept_obj.get("angle")),
        scripts=scripts_rows,
        scenes=scenes_rows,
        metadata=meta_rows,
        thumbnails=thumb_rows,
        videos=videos,
        qc_errors=qc_errors,
        folder=out_dir,
        folder_files=folder_files,
    )


# --- Perfiles ----------------------------------------------------------------
# La ruta /profiles vive en blueprints/profiles.py.


# --- Settings ----------------------------------------------------------------
# La ruta /settings vive en blueprints/settings.py.


# --- Graph (editor y runner) -------------------------------------------------

# Los blueprints del editor de grafo y del runner existen en
# blueprints/graph.py y blueprints/runner.py pero no se registran a
# propósito: el editor y el runner no son accesibles desde la app.


# ---------------------------------------------------------------------------
# Contexto de plantilla
# ---------------------------------------------------------------------------

# Modo manual exclusivo (>= 2.0). Se mantiene la misma forma del dict
# para no tocar las plantillas que aún consultan llm.key / llm.label /
# llm.detail.
LLM_MODE = {
    "key": "manual",
    "label": "Modo manual",
    "detail": "copias los prompts a tu LLM",
    "target": "tu LLM",
}


@app.context_processor
def inject_globals():
    return {
        "app_name": CONFIG["app"]["name"],
        "app_tagline": CONFIG["app"]["tagline"],
        "app_version": CONFIG["app"]["version"],
        "pipeline": pipeline_view,
        "status_label": status_label,
        "timecode": format_timecode,
        "llm": LLM_MODE,
        "is_manual_output": llm_output_is_manual,
        "qc_checks": CONFIG["qc"]["checks"],
    }


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

with app.app_context():
    init_db()

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("  %s — %s", CONFIG["app"]["name"], CONFIG["app"]["tagline"])
    log.info("  v%s", CONFIG["app"]["version"])
    log.info("=" * 60)
    log.info("  Base de datos: %s", DB_PATH)
    log.info("  Exportaciones: %s", PROJECTS_DIR)
    log.info("  Modo: manual (los prompts se copian al LLM externo)")
    log.info("=" * 60)

    # Permitir elegir servidor con variable de entorno:
    #   python app.py              -> dev (Flask/Werkzeug, con debug + autoreload)
    #   python app.py --prod       -> producción (Waitress)
    #   TST_SERVER=waitress python app.py   -> equivalente a --prod
    use_prod = "--prod" in sys.argv or os.environ.get("TST_SERVER") == "waitress"

    if use_prod:
        try:
            from waitress import serve
        except ImportError:
            log.error("waitress no instalado. Ejecuta: pip install waitress")
            sys.exit(1)
        host = os.environ.get("TST_HOST", "0.0.0.0")
        port = int(os.environ.get("TST_PORT", "5000"))
        threads = int(os.environ.get("TST_THREADS", "4"))
        log.info("  Servidor: Waitress (producción) · %s:%s · %s hilos", host, port, threads)
        log.info("  Abre http://localhost:%s en tu navegador", port)
        log.info("=" * 60)
        serve(app, host=host, port=port, threads=threads)
    else:
        log.info("  Servidor: Flask dev (debug) — usa --prod o TST_SERVER=waitress")
        log.info("             para entorno de producción.")
        log.info("  Abre http://localhost:5000 en tu navegador")
        log.info("=" * 60)
        app.run(host="0.0.0.0", port=5000, debug=True)

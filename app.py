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
import sys
import json
import sqlite3
import time
import logging
import urllib.request
import zipfile
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, send_from_directory, abort, session, g,
    has_app_context,
)

from services.parsers import (
    parse_research,
    parse_concept,
    parse_script,
    parse_scenes,
    parse_scenes_tst,
    parse_scenes_json,
    parse_prompt_json,
    parse_metadata,
    parse_thumbnail,
    count_words,
    estimate_duration_seconds,
)
from services.llm import call_llm, _manual_fallback, llm_output_is_manual
from services.qc import run_qc, save_qc_issues

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

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
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

# Blueprints (PoC monolito — T2.2). Ver blueprints/graph.py y
# blueprints/runner.py. Los imports se hacen aqui para que los
# modulos blueprints puedan importar desde app sin ciclos.
from blueprints.graph import graph_bp  # noqa: E402
from blueprints.runner import runner_bp  # noqa: E402
app.register_blueprint(graph_bp)
app.register_blueprint(runner_bp)


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

CREATE TABLE IF NOT EXISTS profile_graph_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    node_key TEXT NOT NULL,
    label TEXT,
    sys_prompt TEXT,
    user_prompt TEXT,
    inputs_json TEXT,
    position_x REAL DEFAULT 0,
    position_y REAL DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    is_fixed INTEGER DEFAULT 0,
    updated_at TEXT,
    UNIQUE(profile_id, node_key),
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS node_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    node_key TEXT NOT NULL,
    output TEXT,
    status TEXT,
    duration_ms INTEGER,
    created_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
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
            "CREATE TABLE IF NOT EXISTS _schema_migrations "
            "(name TEXT PRIMARY KEY, applied_at TEXT)"
        )
        _migrate_stage_prompts_to_profile_prompts(conn)
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


# ---------------------------------------------------------------------------
# Prompts por perfil (graph foundation)
# ---------------------------------------------------------------------------


def resolve_stage_prompt(profile_id: int | None, stage: str) -> tuple[str, str]:
    """Devuelve (sys_prompt, user_prompt) del perfil+stage o fallback a CONFIG.

    Si no hay fila en `profile_prompts` y `stage` está en CONFIG["prompts"],
    devuelve los strings canónicos. Si el stage no existe, devuelve ("", "")
    y registra un aviso por consola.
    """
    if profile_id is not None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT sys_prompt, user_prompt FROM profile_prompts "
                "WHERE profile_id=? AND stage=?",
                (profile_id, stage),
            ).fetchone()
            if row:
                return row["sys_prompt"], row["user_prompt"]
    cfg = CONFIG.get("prompts", {}).get(stage)
    if cfg:
        return cfg.get("system", ""), cfg.get("format", "")
    log.warning("[resolve_stage_prompt] stage '%s' no existe en CONFIG['prompts']", stage)
    return "", ""


def save_profile_prompt(profile_id: int | None, stage: str,
                         sys_prompt: str, user_prompt: str) -> None:
    """UPSERT en `profile_prompts` por (profile_id, stage). No hace nada si profile_id es None."""
    if profile_id is None:
        return
    now = now_iso()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO profile_prompts
                (profile_id, stage, sys_prompt, user_prompt, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, stage) DO UPDATE SET
                sys_prompt=excluded.sys_prompt,
                user_prompt=excluded.user_prompt,
                updated_at=excluded.updated_at
        """, (profile_id, stage, sys_prompt, user_prompt, now))


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
    "research", "concept", "script_long", "script_short", "scenes",
    "metadata_youtube", "metadata_shorts", "thumbnail_long", "thumbnail_short",
]

DEFAULT_NODE_LABELS = {
    "research": "Investigación",
    "concept": "Concepto",
    "script_long": "Guion 5 min",
    "script_short": "Guion 1 min",
    "scenes": "Escenas",
    "metadata_youtube": "Metadata YouTube",
    "metadata_shorts": "Metadata Shorts",
    "thumbnail_long": "Miniatura 16:9",
    "thumbnail_short": "Miniatura 9:16",
}

DEFAULT_NODE_POSITIONS = {
    "research": (0.0, 0.0),
    "concept": (280.0, 0.0),
    "script_long": (560.0, 0.0),
    "script_short": (560.0, 180.0),
    "scenes": (840.0, 90.0),
    "metadata_youtube": (1120.0, 0.0),
    "metadata_shorts": (1120.0, 180.0),
    "thumbnail_long": (1400.0, 0.0),
    "thumbnail_short": (1400.0, 180.0),
}

DEFAULT_EDGES = [
    ("research", "concept"),
    ("concept", "script_long"),
    ("concept", "script_short"),
    ("script_long", "scenes"),
    ("script_short", "scenes"),
    ("script_long", "metadata_youtube"),
    ("script_short", "metadata_shorts"),
    ("script_long", "thumbnail_long"),
    ("script_short", "thumbnail_short"),
]

MAX_OUTPUT_BYTES = 50 * 1024


def get_or_create_fixed_graph_nodes(profile_id: int | None) -> list[dict]:
    """Asegura las 9 filas fijas y devuelve todas como lista de dicts."""
    if not profile_id:
        return []
    with get_db() as conn:
        existing = [dict(r) for r in conn.execute(
            "SELECT * FROM profile_graph_nodes "
            "WHERE profile_id=? AND is_fixed=1",
            (profile_id,),
        ).fetchall()]
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
            conn.execute("""
                INSERT INTO profile_graph_nodes
                    (profile_id, node_key, label, sys_prompt, user_prompt,
                     inputs_json, position_x, position_y, sort_order,
                     is_fixed, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                profile_id, key,
                DEFAULT_NODE_LABELS.get(key, key),
                default_sys, default_user, "[]", x, y,
                KNOWN_FIXED_NODE_KEYS.index(key),
                now,
            ))
        return [dict(r) for r in conn.execute(
            "SELECT * FROM profile_graph_nodes "
            "WHERE profile_id=? AND is_fixed=1 ORDER BY sort_order, id",
            (profile_id,),
        ).fetchall()]


def fetch_graph_nodes(profile_id: int | None) -> list[dict]:
    if not profile_id:
        return []
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM profile_graph_nodes WHERE profile_id=? "
            "ORDER BY sort_order, id",
            (profile_id,),
        ).fetchall()]


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
            rows = [dict(r) for r in conn.execute(
                "SELECT node_key, inputs_json FROM profile_graph_nodes "
                "WHERE profile_id=?",
                (profile_id,),
            ).fetchall()]
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
            edges.append({
                "id": f"e_{src}_{r['node_key']}_{i}",
                "source": str(src),
                "target": r["node_key"],
            })
            seen.add(key)
    return edges


def save_graph_node(profile_id: int, node_key: str, label: str,
                    sys_prompt: str, user_prompt: str,
                    inputs_json: str, position_x: float,
                    position_y: float, is_fixed: bool) -> dict:
    """UPSERT en profile_graph_nodes; devuelve el dict persistido."""
    now = now_iso()
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM profile_graph_nodes "
            "WHERE profile_id=? AND node_key=?",
            (profile_id, node_key),
        ).fetchone()
        if row:
            conn.execute("""
                UPDATE profile_graph_nodes
                SET label=?, sys_prompt=?, user_prompt=?, inputs_json=?,
                    position_x=?, position_y=?, is_fixed=?, updated_at=?
                WHERE id=?
            """, (
                label, sys_prompt, user_prompt, inputs_json,
                float(position_x), float(position_y),
                1 if is_fixed else 0, now, row["id"],
            ))
            return dict(conn.execute(
                "SELECT * FROM profile_graph_nodes WHERE id=?",
                (row["id"],),
            ).fetchone())
        conn.execute("""
            INSERT INTO profile_graph_nodes
                (profile_id, node_key, label, sys_prompt, user_prompt,
                 inputs_json, position_x, position_y, sort_order,
                 is_fixed, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile_id, node_key, label, sys_prompt, user_prompt,
            inputs_json, float(position_x), float(position_y),
            0, 1 if is_fixed else 0, now,
        ))
        new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        return dict(conn.execute(
            "SELECT * FROM profile_graph_nodes WHERE id=?",
            (new_id,),
        ).fetchone())


def delete_graph_node(profile_id: int, node_key: str) -> bool:
    """Borra un nodo NO fijo. Devuelve True si se borró una fila."""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM profile_graph_nodes "
            "WHERE profile_id=? AND node_key=? AND is_fixed=0",
            (profile_id, node_key),
        )
        return cur.rowcount > 0


def update_graph_layout(profile_id: int,
                        nodes_data: list[dict]) -> int:
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
                    now, profile_id, str(nk),
                ),
            )
            count += cur.rowcount
    return count


def _interpolate_inputs(template: str, project_id: int,
                        inputs: list[str]) -> str:
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
            log.warning("_interpolate_inputs: no se pudo leer node_executions para project=%s inputs=%s: %s",
                        project_id, inputs, e)
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


def _persist_fixed_result(project_id: int, node_key: str, raw: str) -> None:
    """Best-effort: persiste el raw en la tabla del stage correspondiente."""
    now = now_iso()
    with get_db() as conn:
        if node_key == "research":
            parsed = parse_research(raw)
            conn.execute("""
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
            """, (
                project_id, parsed["content"] or raw,
                json.dumps(parsed["sources"], ensure_ascii=False),
                json.dumps(parsed["facts"], ensure_ascii=False),
                json.dumps(parsed["theories"], ensure_ascii=False),
                json.dumps(parsed["unverified"], ensure_ascii=False),
                now,
            ))
        elif node_key == "concept":
            parsed = parse_concept(raw)
            conn.execute("""
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
            """, (
                project_id, parsed["angle"] or raw,
                parsed["thesis"],
                json.dumps(parsed["key_points"], ensure_ascii=False),
                parsed["emotional_hook"],
                json.dumps(parsed["what_they_learn"], ensure_ascii=False),
                json.dumps(parsed["what_they_feel"], ensure_ascii=False),
                json.dumps(parsed["risks"], ensure_ascii=False),
                now,
            ))
        elif node_key in ("script_long", "script_short"):
            stype = "long" if node_key == "script_long" else "short"
            parsed = parse_script(raw, stype)
            body = parsed["body_full"] or raw
            wc = count_words(body)
            existing = conn.execute(
                "SELECT id FROM scripts WHERE project_id=? AND type=?",
                (project_id, stype),
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
                    body, wc, now, existing["id"],
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
                    parsed["cta"], body, wc, now,
                ))
        elif node_key == "scenes":
            parsed = parse_scenes(raw) or []
            target = conn.execute(
                "SELECT id FROM scripts WHERE project_id=? AND type='long'",
                (project_id,),
            ).fetchone()
            sid = target["id"] if target else None
            if sid is not None and parsed:
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
                total_words = sum(
                    count_words(sc.get("narration_segment", "")) for sc in parsed
                )
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
                    conn.execute("""
                        INSERT INTO scenes (project_id, script_id, scene_number,
                            narration, visual_description, camera_movement,
                            transition, duration_seconds, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        project_id, sid, scene_num,
                        sc.get("narration_segment", ""),
                        sc.get("image_prompt", "")
                            or sc.get("visual_description", ""),
                        sc.get("camera_movement", "") or "",
                        sc.get("transition", "") or "",
                        dur, now,
                    ))
        elif node_key in ("metadata_youtube", "metadata_shorts",
                          "metadata_youtube_long", "metadata_youtube_short",
                          "metadata_facebook_long", "metadata_reels_short"):
            platform = {
                "metadata_youtube": "youtube_long",
                "metadata_shorts": "youtube_short",
                "metadata_youtube_long": "youtube_long",
                "metadata_youtube_short": "youtube_short",
                "metadata_facebook_long": "facebook_long",
                "metadata_reels_short": "reels_short",
            }[node_key]
            parsed = parse_metadata(raw, platform)
            existing = conn.execute(
                "SELECT id FROM metadata_records WHERE project_id=? AND platform=?",
                (project_id, platform),
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
                """, (*fields, now, existing["id"]))
            else:
                conn.execute("""
                    INSERT INTO metadata_records (project_id, platform, titles,
                        description, chapters, tags, hashtags, caption, hook,
                        cta, on_screen_text, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (project_id, platform, *fields, now))
        elif node_key in ("thumbnail_long", "thumbnail_short"):
            stype = "long" if node_key == "thumbnail_long" else "short"
            parsed = parse_thumbnail(raw, stype)
            prompt_text = (parsed.get("prompt") or "").strip() or raw.strip()
            existing = conn.execute(
                "SELECT id FROM thumbnail_records "
                "WHERE project_id=? AND script_type=?",
                (project_id, stype),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE thumbnail_records SET prompt=?, updated_at=? WHERE id=?",
                    (prompt_text, now, existing["id"]),
                )
            else:
                conn.execute("""
                    INSERT INTO thumbnail_records
                        (project_id, script_type, prompt, updated_at)
                    VALUES (?, ?, ?, ?)
                """, (project_id, stype, prompt_text, now))


def _load_first_script(project_id: int, script_type: str) -> dict:
    """Devuelve el primer guion del tipo pedido o un dict vacío con campos clave."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM scripts WHERE project_id=? AND type=? LIMIT 1",
            (project_id, script_type),
        ).fetchone()
        if row:
            return dict(row)
    return {"title": "", "hook": "", "body_full": "", "word_count": 0,
            "context": "", "development": "", "revelations": "",
            "conclusion": "", "cta": ""}


def _build_user_msg_for_fixed(project_id: int, profile: dict | None,
                              project: dict, node_key: str) -> str:
    """Construye el user_msg para un nodo fijo."""
    if node_key == "research":
        _, user_msg = build_research_prompt(project, profile)
        return user_msg
    if node_key == "concept":
        with get_db() as conn:
            research_obj = fetch_optional_dict(
                conn, "SELECT * FROM research WHERE project_id=?",
                (project_id,),
            )
        _, user_msg = build_concept_prompt(project, profile, research_obj)
        return user_msg
    if node_key == "script_long":
        with get_db() as conn:
            research_obj = fetch_optional_dict(
                conn, "SELECT * FROM research WHERE project_id=?",
                (project_id,),
            )
            concept_obj = fetch_optional_dict(
                conn, "SELECT * FROM concept WHERE project_id=?",
                (project_id,),
            )
        _, user_msg = build_script_prompt(
            project, profile, research_obj, concept_obj, "long",
        )
        return user_msg
    if node_key == "script_short":
        with get_db() as conn:
            research_obj = fetch_optional_dict(
                conn, "SELECT * FROM research WHERE project_id=?",
                (project_id,),
            )
            concept_obj = fetch_optional_dict(
                conn, "SELECT * FROM concept WHERE project_id=?",
                (project_id,),
            )
        _, user_msg = build_script_prompt(
            project, profile, research_obj, concept_obj, "short",
        )
        return user_msg
    if node_key == "scenes":
        script = _load_first_script(project_id, "long")
        _, user_msg = build_scenes_prompt(project, profile, script)
        return user_msg
    if node_key == "metadata_youtube":
        script = _load_first_script(project_id, "long")
        _, user_msg = build_metadata_prompt(project, profile, script, "youtube")
        return user_msg
    if node_key == "metadata_shorts":
        script = _load_first_script(project_id, "short")
        _, user_msg = build_metadata_prompt(project, profile, script, "shorts")
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
                "SELECT * FROM projects WHERE id=?", (project_id,),
            ).fetchone()
            if proj is None:
                return {"ok": False, "status": "error",
                        "error": "Proyecto no encontrado"}
            project = dict(proj)
        profile = get_profile(project["profile_id"]) or get_default_profile()
        profile_id = profile["id"] if profile else None
        node_row = None
        if profile_id:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT * FROM profile_graph_nodes "
                    "WHERE profile_id=? AND node_key=?",
                    (profile_id, node_key),
                ).fetchone()
            node_row = dict(row) if row else None

        if node_key in KNOWN_FIXED_NODE_KEYS:
            sys_p, _ = resolve_stage_prompt(profile_id, node_key)
            user_msg = _build_user_msg_for_fixed(
                project_id, profile, project, node_key,
            )
            raw = call_llm(sys_p, user_msg)
            _persist_fixed_result(project_id, node_key, raw)
        else:
            if not node_row:
                return {"ok": False, "status": "error",
                        "error": "Nodo personalizado no encontrado"}
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
            conn.execute("""
                INSERT INTO node_executions
                    (project_id, node_key, output, status, duration_ms, created_at)
                VALUES (?, ?, ?, 'ok', ?, ?)
            """, (project_id, node_key, raw, duration_ms, now_iso()))
            last = conn.execute(
                "SELECT id, status, duration_ms, created_at FROM node_executions "
                "WHERE id=last_insert_rowid()"
            ).fetchone()
        return {
            "ok": True, "status": "ok", "output": raw,
            "node_executions": dict(last) if last else {},
        }
    except Exception as e:
        log.exception("execute_graph_node falló project=%s node=%s", project_id, node_key)
        msg = str(e)[:4096]
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO node_executions
                        (project_id, node_key, output, status, created_at)
                    VALUES (?, ?, ?, 'error', ?)
                """, (project_id, node_key, msg, now_iso()))
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


def count_words(text: str | None) -> int:
    if not text:
        return 0
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def estimate_duration_seconds(text: str | None, wpm: int = 150) -> int:
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
            n_unresolved = conn.execute(
                "SELECT COUNT(*) AS n FROM qc_issues "
                "WHERE project_id=? AND resolved=0",
                (project["id"],),
            ).fetchone()["n"]
            qc_done = n_unresolved > 0
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
        except Exception as e:
            # expected: key_points puede venir como string ya formateado;
            # el json.loads falla y caemos al string original.
            log.debug("key_points no es JSON, se usa como string: %s", e)

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
    """Resuelve (system, format) para la plataforma pedida.

    Las plataformas válidas son ``youtube_long``, ``facebook_long``,
    ``youtube_short`` y ``reels_short``. Mantiene retrocompatibilidad con los
    nombres antiguos ``youtube`` y ``shorts``.
    """
    legacy = {"youtube": "metadata_youtube", "shorts": "metadata_shorts"}
    key = (
        f"metadata_{platform}"
        if f"metadata_{platform}" in CONFIG.get("prompts", {})
        else legacy.get(platform, f"metadata_{platform}")
    )
    cfg = CONFIG["prompts"].get(key)
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
        try:
            sync_project_folder(new_id)
        except Exception as e:
            log.exception("[sync_project_folder] create project %s", new_id)
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
    saved_prompts = list_profile_prompts(project["profile_id"])
    return render_template("project.html", project=project, profile=profile,
                           saved_prompts=saved_prompts)


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
def delete_project(project_id):
    with get_db() as conn:
        row = conn.execute("SELECT name FROM projects WHERE id=?",
                           (project_id,)).fetchone()
        name = row["name"] if row else None
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    if name:
        try:
            delete_project_folder(project_id, name)
        except Exception as e:
            log.exception("[delete_project_folder] %s", project_id)
    flash("Proyecto eliminado", "ok")
    return redirect(url_for("dashboard"))


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
            return render_template("research.html", project=project, profile=profile,
                                   research=research_obj, generated=generated,
                                   sys_prompt=sys_p, user_prompt=user_p)
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
                flash("Investigación guardada", "ok")
            try:
                sync_project_folder(project_id)
            except Exception as e:
                log.exception("[sync_project_folder] research %s", project_id)
            return redirect(url_for("research", project_id=project_id))

    sources = json.loads(research_obj.get("sources") or "[]")
    facts = json.loads(research_obj.get("facts") or "[]")
    return render_template("research.html", project=project, profile=profile,
                           research=research_obj, sources=sources, facts=facts)


# --- Concepto ----------------------------------------------------------------

@app.route("/projects/<int:project_id>/concept", methods=["GET", "POST"])
def concept(project_id):
    with get_db() as conn:
        project = fetch_project_or_404(project_id)
        profile = get_profile(project["profile_id"])
        research_obj = fetch_optional_dict(conn, "SELECT * FROM research WHERE project_id=?", (project_id,))
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
            return render_template("concept.html", project=project, profile=profile,
                                   concept=concept_obj, generated=generated,
                                   sys_prompt=sys_p, user_prompt=user_p)
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
                flash("Concepto guardado", "ok")
            try:
                sync_project_folder(project_id)
            except Exception as e:
                log.exception("[sync_project_folder] concept %s", project_id)
            return redirect(url_for("concept", project_id=project_id))

    key_points = json.loads(concept_obj.get("key_points") or "[]")
    return render_template("concept.html", project=project, profile=profile,
                           concept=concept_obj, key_points=key_points)


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

    if request.method == "POST":
        action = request.form.get("action")
        stype = request.form.get("script_type")
        if action == "generate_prompt" and stype in ("long", "short"):
            if not concept_obj or not concept_obj.get("angle"):
                flash("Necesitas un concepto antes de generar el guion", "error")
                return redirect(url_for("concept", project_id=project_id))
            sys_p, user_p = build_script_prompt(project, profile, research_obj, concept_obj, stype)
            save_profile_prompt(project["profile_id"], f"script_{stype}", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template("scripts.html", project=project, profile=profile,
                                   long_s=long_s, short_s=short_s,
                                   generated=generated, gen_type=stype,
                                   sys_prompt=sys_p, user_prompt=user_p)
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
                flash(f"Guion {stype} guardado", "ok")
            try:
                sync_project_folder(project_id)
            except Exception as e:
                log.exception("[sync_project_folder] scripts %s", project_id)
            return redirect(url_for("scripts", project_id=project_id))

    return render_template("scripts.html", project=project, profile=profile,
                           long_s=long_s, short_s=short_s)


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
            save_profile_prompt(project["profile_id"], "scenes", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template("scenes.html", project=project, profile=profile,
                                   scripts=scripts_rows, scenes=scenes_rows,
                                   generated=generated, gen_script_id=script_id,
                                   sys_prompt=sys_p, user_prompt=user_p,
                                   active_script_id=script_id)
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
                        except (TypeError, ValueError) as e:
                            # expected: scene_number puede no ser numerico.
                            log.debug("scene_number no numerico: %s", e)
                            scene_num = 0
                        try:
                            dur = int(sc.get("duration_seconds", 0))
                        except (TypeError, ValueError) as e:
                            log.debug("duration_seconds no numerico: %s", e)
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
                flash(f"Guardadas {len(parsed)} escenas del guion seleccionado", "ok")
            try:
                sync_project_folder(project_id)
            except Exception as e:
                log.exception("[sync_project_folder] scenes %s", project_id)
            return redirect(url_for("scenes", project_id=project_id, script_id=script_id))
        elif action == "delete":
            scene_id = request.form.get("scene_id")
            with get_db() as conn:
                conn.execute("DELETE FROM scenes WHERE id=?", (scene_id,))
            return redirect(url_for("scenes", project_id=project_id, script_id=active_script_id))

    return render_template("scenes.html", project=project, profile=profile,
                           scripts=scripts_rows, scenes=scenes_rows,
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

    valid_platforms = ("youtube_long", "facebook_long",
                       "youtube_short", "reels_short")

    if request.method == "POST":
        action = request.form.get("action")
        platform = request.form.get("platform")
        if action == "generate_prompt" and platform in valid_platforms:
            script_id = request.form.get("script_id")
            script = next((s for s in scripts_rows if str(s["id"]) == str(script_id)), None)
            if not script:
                flash("Selecciona un guion", "error")
                return redirect(url_for("metadata", project_id=project_id))
            sys_p, user_p = build_metadata_prompt(project, profile, script, platform)
            save_profile_prompt(project["profile_id"], f"metadata_{platform}", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template("metadata.html", project=project, profile=profile,
                                   scripts=scripts_rows, meta_by_platform=meta_by_platform,
                                   generated=generated, gen_platform=platform,
                                   gen_script_id=script_id,
                                   sys_prompt=sys_p, user_prompt=user_p,
                                   saved_yt_long=list_profile_prompts(project["profile_id"]).get("metadata_youtube_long"),
                                   saved_fb_long=list_profile_prompts(project["profile_id"]).get("metadata_facebook_long"),
                                   saved_yt_short=list_profile_prompts(project["profile_id"]).get("metadata_youtube_short"),
                                   saved_reels_short=list_profile_prompts(project["profile_id"]).get("metadata_reels_short"))
        elif action == "save" and platform in valid_platforms:
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
                flash(f"Metadata {platform} guardada", "ok")
            try:
                sync_project_folder(project_id)
            except Exception as e:
                log.exception("[sync_project_folder] metadata %s", project_id)
            return redirect(url_for("metadata", project_id=project_id))

    for m in meta_by_platform.values():
        m["titles_list"] = json.loads(m.get("titles") or "[]")
        m["chapters_list"] = json.loads(m.get("chapters") or "[]")
        m["tags_list"] = json.loads(m.get("tags") or "[]")
        m["hashtags_list"] = json.loads(m.get("hashtags") or "[]")
        m["on_screen_list"] = json.loads(m.get("on_screen_text") or "[]")

    saved_prompts = list_profile_prompts(project["profile_id"])
    return render_template(
        "metadata.html", project=project, profile=profile,
        scripts=scripts_rows, meta_by_platform=meta_by_platform,
        saved_yt_long=saved_prompts.get("metadata_youtube_long"),
        saved_fb_long=saved_prompts.get("metadata_facebook_long"),
        saved_yt_short=saved_prompts.get("metadata_youtube_short"),
        saved_reels_short=saved_prompts.get("metadata_reels_short"),
    )


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
            save_profile_prompt(project["profile_id"], f"thumbnail_{script_type}", sys_p, user_p)
            generated = call_llm(sys_p, user_p)
            return render_template("thumbnails.html", project=project, profile=profile,
                                   scripts=scripts_rows,
                                   thumb_by_type=thumb_by_type,
                                   generated=generated, gen_type=script_type,
                                   gen_script_id=script_id,
                                   sys_prompt=sys_p, user_prompt=user_p)
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
                flash(f"Miniatura {script_type} guardada", "ok")
                try:
                    sync_project_folder(project_id)
                except Exception as e:
                    log.exception("[sync_project_folder] thumbnails %s", project_id)
            return redirect(url_for("thumbnails", project_id=project_id))

    return render_template("thumbnails.html", project=project, profile=profile,
                           scripts=scripts_rows, thumb_by_type=thumb_by_type)


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
        try:
            sync_project_folder(project_id)
        except Exception as e:
            log.exception("[sync_project_folder] qc %s", project_id)
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


# --- Export / sincronización de carpeta ---------------------------------------

def safe_project_dir(project_id: int, name: str) -> Path:
    """Devuelve la ruta canónica de la carpeta del proyecto en ``PROJECTS_DIR``.

    El nombre se sanitiza para que sea seguro en sistemas de archivos y se le
    añade el id (único) para evitar colisiones entre proyectos con el mismo
    nombre.
    """
    safe_name = re.sub(r"[^\w\-]+", "_", name).strip("_") or f"proyecto_{project_id}"
    return PROJECTS_DIR / f"{safe_name}_{project_id}"


def delete_project_folder(project_id: int, name: str) -> None:
    """Borra la carpeta del proyecto en disco (si existe). Idempotente."""
    folder = safe_project_dir(project_id, name)
    if folder.exists():
        shutil.rmtree(folder)


def sync_project_folder(project_id: int) -> tuple[Path, list[str]]:
    """Reconstruye en disco la carpeta del proyecto a partir de la BD.

    Es idempotente: borra el contenido previo de la carpeta y lo regenera.
    Devuelve ``(carpeta, lista_de_rutas_relativas)`` para que el caller
    pueda listar los archivos o construir un ZIP a demanda.

    El contrato de archivos es estable:
        00_RESUMEN.md
        01_investigacion.md
        02_concepto.md
        03_guiones/guion_{long,short}.md
        04_escenas/escenas.md
        05_metadata/metadata_{platform}.md
        06_thumbnails/thumbnail_{long,short}.md
        07_prompts_usados.md
        08_paquete_completo.json
    """
    with get_db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=?",
                               (project_id,)).fetchone()
        if not project:
            return PROJECTS_DIR / "_missing", []
        project = dict(project)
        profile = get_profile(project["profile_id"])
        research_obj = fetch_optional_dict(conn,
            "SELECT * FROM research WHERE project_id=?", (project_id,))
        concept_obj = fetch_optional_dict(conn,
            "SELECT * FROM concept WHERE project_id=?", (project_id,))
        scripts_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM scripts WHERE project_id=?", (project_id,)
        ).fetchall()]
        scenes_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM scenes WHERE project_id=? ORDER BY scene_number",
            (project_id,)
        ).fetchall()]
        meta_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM metadata_records WHERE project_id=?", (project_id,)
        ).fetchall()]
        thumb_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM thumbnail_records WHERE project_id=?", (project_id,)
        ).fetchall()]

    out_dir = safe_project_dir(project_id, project["name"])
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    written: list[str] = []

    # 00_RESUMEN.md
    rel = "00_RESUMEN.md"
    with open(out_dir / rel, "w", encoding="utf-8") as f:
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
    written.append(rel)

    # 01_investigacion.md
    if research_obj and research_obj.get("content"):
        rel = "01_investigacion.md"
        with open(out_dir / rel, "w", encoding="utf-8") as f:
            f.write(f"# Investigación — {project['name']}\n\n")
            f.write((research_obj.get("content") or "") + "\n\n")
            sources = json.loads(research_obj.get("sources") or "[]")
            if sources:
                f.write("## Fuentes\n\n")
                for s in sources:
                    f.write(f"- {s}\n")
        written.append(rel)

    # 02_concepto.md
    if concept_obj and concept_obj.get("angle"):
        rel = "02_concepto.md"
        with open(out_dir / rel, "w", encoding="utf-8") as f:
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
        written.append(rel)

    # 03_guiones/
    if scripts_rows:
        gdir = out_dir / "03_guiones"
        gdir.mkdir(exist_ok=True)
        for s in scripts_rows:
            rel = f"03_guiones/guion_{s['type']}.md"
            with open(gdir / Path(rel).name, "w", encoding="utf-8") as f:
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
            written.append(rel)

    # 04_escenas/
    if scenes_rows:
        edir = out_dir / "04_escenas"
        edir.mkdir(exist_ok=True)
        rel = "04_escenas/escenas.md"
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
        written.append(rel)

    # 05_metadata/
    if meta_rows:
        mdir = out_dir / "05_metadata"
        mdir.mkdir(exist_ok=True)
        for m in meta_rows:
            rel = f"05_metadata/metadata_{m['platform']}.md"
            with open(mdir / f"metadata_{m['platform']}.md", "w", encoding="utf-8") as f:
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
            written.append(rel)

    # 06_thumbnails/
    if thumb_rows:
        tdir = out_dir / "06_thumbnails"
        tdir.mkdir(exist_ok=True)
        for t in thumb_rows:
            stype = t["script_type"]
            aspect = "16:9 (horizontal)" if stype == "long" else "9:16 (vertical)"
            rel = f"06_thumbnails/thumbnail_{stype}.md"
            with open(tdir / f"thumbnail_{stype}.md", "w", encoding="utf-8") as f:
                f.write(f"# Miniatura — guion {stype} ({aspect})\n\n")
                f.write(f"_Actualizado: {t['updated_at']}_\n\n")
                f.write("```\n")
                f.write((t.get("prompt") or "").strip())
                f.write("\n```\n")
            written.append(rel)

    # 07_prompts_usados.md
    stage_prompts = list_profile_prompts(project["profile_id"])
    if stage_prompts:
        stage_labels = {
            "research": "Investigación",
            "concept": "Concepto",
            "script_long": "Guion 5 min",
            "script_short": "Guion 1 min",
            "scenes": "Escenas",
            "metadata_youtube": "Metadata YouTube",
            "metadata_shorts": "Metadata Shorts",
            "metadata_youtube_long": "Metadata YouTube 5 min",
            "metadata_youtube_short": "Metadata YouTube 1 min",
            "metadata_facebook_long": "Metadata Facebook 5 min",
            "metadata_reels_short": "Metadata Reels 1 min",
            "thumbnail_long": "Miniatura 5 min",
            "thumbnail_short": "Miniatura 1 min",
        }
        rel = "07_prompts_usados.md"
        with open(out_dir / rel, "w", encoding="utf-8") as f:
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
        written.append(rel)

    # 08_paquete_completo.json
    rel = "08_paquete_completo.json"
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
    with open(out_dir / rel, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
    written.append(rel)

    return out_dir, written


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
        return send_file(zip_path, as_attachment=True,
                         download_name=zip_path.name)

    # GET: sincroniza si la carpeta no existe todavía y muestra el estado
    if not out_dir.exists():
        out_dir, written = sync_project_folder(project_id)
    folder_files = sorted(p.name + ("/" if p.is_dir() else "")
                          for p in out_dir.rglob("*") if p != out_dir)

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
                           qc_errors=qc_errors,
                           folder=out_dir,
                           folder_files=folder_files)


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
        elif action == "update":
            pid = request.form.get("profile_id")
            name = request.form.get("name", "").strip()
            if not pid:
                flash("Falta el perfil a actualizar", "error")
                return redirect(url_for("profiles"))
            if not name:
                flash("El nombre del perfil es obligatorio", "error")
                return redirect(url_for("profiles"))
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
        return redirect(url_for("profiles"))
    with get_db() as conn:
        profiles_list = [dict(r) for r in conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()]
    for p in profiles_list:
        try:
            p["platforms_list"] = json.loads(p.get("platforms") or "[]")
        except Exception as e:
            # expected: platforms puede ser un string legacy; caemos a
            # lista vacía y el formulario se renderiza sin opciones.
            log.debug("platforms no parseable en perfil %s: %s", p.get("id"), e)
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


# --- Graph (editor y runner) -------------------------------------------------

# Las 7 rutas del editor de grafo y del runner viven ahora en
# blueprints/graph.py y blueprints/runner.py (T2.2). Aqui solo se
# conserva el grueso de las rutas del monolito.


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

with app.app_context():
    init_db()

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("  %s — %s", CONFIG["app"]["name"], CONFIG["app"]["tagline"])
    log.info("  v%s", CONFIG["app"]["version"])
    log.info("=" * 60)
    log.info("  Base de datos: %s", DB_PATH)
    log.info("  Exportaciones: %s", PROJECTS_DIR)
    log.info("  LLM provider: %s", CONFIG["llm"]["provider"])
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

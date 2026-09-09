"""Recover the 7 real projects from projects/ back into workflow.db.

Single transaction. On failure the DB stays untouched (the backup in
backups/ is the safety net). See top-of-file mapping rules.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from app import DB_PATH, get_db, now_iso  # noqa: E402

REAL_PREFIXES = {
    1: "Todo_sobre_los_Fosiles",
    9: "Todo_sobre_los_arboles_gigantes",
    11: "Todo_sobre_los_Denisovanos",
    12: "Todo_sobre_la_Ant",
    13: "Todo_sobre_La_Piedra_R",
    14: "Todo_sobre_Jacobo_Grinberg",
    15: "Todo_sobre_Stonehenge",
}

FORCED_STATUS = {
    1: "ready",
    9: "ready",
    11: "thumbnails",
    12: "metadata",
    13: "metadata",
    14: "scripts",
    15: "metadata",
}

ROADMAP_ORDER = ("research", "concept", "scripts", "scenes", "metadata", "thumbnails", "qc")


def find_folder(pid: int, prefix: str) -> Path:
    base = ROOT / "projects"
    suffix = f"_{pid}"
    for d in os.listdir(base):
        if d.endswith(suffix) and d.startswith(prefix) and (base / d).is_dir():
            return base / d
    raise FileNotFoundError(f"No folder for id={pid} prefix={prefix!r}")


def backup_db() -> Path:
    backups = ROOT / "backups"
    backups.mkdir(exist_ok=True)
    ts = now_iso().replace(":", "-").replace(".", "-")
    target = backups / f"workflow_pre_recovery_{ts}.db"
    shutil.copy2(DB_PATH, target)
    return target


# --- Legacy per-stage builders ---------------------------------------------


def _stage_prompt(sp: dict, *keys: str) -> str:
    parts: list[str] = []
    for k in keys:
        entry = sp.get(k)
        if not entry:
            continue
        sys_p = (entry.get("sys_prompt") or "").strip()
        usr_p = (entry.get("user_prompt") or "").strip()
        text = sys_p
        if usr_p:
            text = (text + "\n\n" + usr_p).strip() if text else usr_p
        if text and (not parts or parts[-1] != text):
            if len(keys) > 1:
                label = entry.get("label") or k
                parts.append(f"# {label}\n\n{text}")
            else:
                parts.append(text)
    return "\n\n---\n\n".join(parts)


def _research_response(research: dict | None) -> str:
    if not research:
        return ""
    out = (research.get("content") or "").strip()
    if not out:
        return ""
    extra: list[str] = []
    for key, title in (
        ("facts", "Hechos confirmados"),
        ("theories", "Teorías y versiones"),
        ("unverified", "Por verificar"),
    ):
        v = research.get(key)
        if not v:
            continue
        try:
            items = json.loads(v) if isinstance(v, str) else v
        except json.JSONDecodeError:
            items = []
        if items:
            extra.append(f"## {title}\n\n" + "\n".join(f"- {x}" for x in items))
    sources_raw = research.get("sources")
    if sources_raw:
        try:
            srcs = json.loads(sources_raw) if isinstance(sources_raw, str) else sources_raw
        except json.JSONDecodeError:
            srcs = []
        if srcs:
            extra.append("## Fuentes\n\n" + "\n".join(f"- {s}" for s in srcs))
    if extra:
        out = out + "\n\n" + "\n\n".join(extra)
    return out


def _concept_response(concept: dict | None) -> str:
    if not concept:
        return ""
    parts: list[str] = []
    for key, title in (
        ("angle", "Ángulo"),
        ("thesis", "Tesis"),
        ("emotional_hook", "Gancho emocional"),
    ):
        v = (concept.get(key) or "").strip()
        if v:
            parts.append(f"## {title}\n\n{v}")
    for key, title in (
        ("key_points", "Puntos clave"),
        ("what_they_learn", "Qué aprenden"),
        ("what_they_feel", "Qué sienten"),
        ("risks", "Riesgos"),
    ):
        v = concept.get(key)
        if not v:
            continue
        try:
            items = json.loads(v) if isinstance(v, str) else v
        except json.JSONDecodeError:
            items = []
        if items:
            rendered = "\n".join(
                f"{i}. {x}" if key == "key_points" else f"- {x}"
                for i, x in enumerate(items, 1)
            )
            parts.append(f"## {title}\n\n{rendered}")
    return "\n\n".join(parts)


def _scripts_response(scripts: list[dict]) -> str:
    if not scripts:
        return ""
    blocks: list[str] = []
    by_type = {s.get("type"): s for s in scripts}
    for stype, header in (("long", "Guion 5 min"), ("short", "Guion 1 min")):
        s = by_type.get(stype)
        if not s:
            continue
        title = s.get("title") or ""
        body = (s.get("body_full") or s.get("development") or "").strip()
        if not body and not title:
            continue
        head = f"## {header}"
        if title:
            head += f" — {title}"
        blocks.append(head + "\n\n" + body)
    return "\n\n---\n\n".join(blocks)


def _scenes_response(scenes: list[dict]) -> str:
    if not scenes:
        return ""
    lines: list[str] = []
    for s in scenes:
        n = s.get("scene_number")
        narration = (s.get("narration") or "").strip()
        visual = (s.get("visual_description") or "").strip()
        cam = s.get("camera_movement") or ""
        tr = s.get("transition") or ""
        dur = s.get("duration_seconds") or 0
        lines.append(f"## ESCENA {n}")
        lines.append(f"**TEXTO AUDIO:** {narration}")
        lines.append(f"**IMAGEN:** {visual}")
        lines.append(f"_Cámara: {cam} · Transición: {tr} · Duración: {dur}s_")
        lines.append("")
    return "\n".join(lines).strip()


def _metadata_response(meta: list[dict]) -> str:
    if not meta:
        return ""
    blocks: list[str] = []
    for m in meta:
        platform = m.get("platform") or ""
        parts: list[str] = [f"# {platform}"]
        titles_raw = m.get("titles")
        if titles_raw:
            try:
                titles = json.loads(titles_raw) if isinstance(titles_raw, str) else titles_raw
            except json.JSONDecodeError:
                titles = []
            if titles:
                parts.append("## Títulos\n\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(titles, 1)))
        desc = (m.get("description") or "").strip()
        if desc:
            parts.append(f"## Descripción\n\n{desc}")
        for key, title in (
            ("chapters", "Capítulos"),
            ("tags", "Tags"),
            ("hashtags", "Hashtags"),
            ("on_screen_text", "Texto en pantalla"),
        ):
            v = m.get(key)
            if not v:
                continue
            try:
                items = json.loads(v) if isinstance(v, str) else v
            except json.JSONDecodeError:
                items = []
            if items:
                if key in ("tags", "hashtags"):
                    parts.append(f"## {title}\n\n{', '.join(items)}")
                else:
                    parts.append(f"## {title}\n\n" + "\n".join(f"- {x}" for x in items))
        for key, title in (
            ("caption", "Caption"),
            ("hook", "Hook"),
            ("cta", "CTA"),
        ):
            v = (m.get(key) or "").strip()
            if v:
                parts.append(f"## {title}\n\n{v}")
        blocks.append("\n\n".join(parts))
    return "\n\n---\n\n".join(blocks)


def _thumbnails_response(thumbs: list[dict]) -> str:
    if not thumbs:
        return ""
    blocks: list[str] = []
    for t in thumbs:
        stype = t.get("script_type") or ""
        prompt = (t.get("prompt") or "").strip()
        blocks.append(f"# Miniatura {stype}\n\n```\n{prompt}\n```")
    return "\n\n---\n\n".join(blocks)


def build_legacy_stages(bundle: dict) -> dict[str, dict[str, str]]:
    sp = bundle.get("stage_prompts") or {}

    def merge_prompt(*keys: str) -> str:
        present = [k for k in keys if sp.get(k)]
        if not present:
            return ""
        blocks: list[str] = []
        for k in present:
            entry = sp[k]
            sys_p = (entry.get("sys_prompt") or "").strip()
            usr_p = (entry.get("user_prompt") or "").strip()
            text = sys_p
            if usr_p:
                text = (text + "\n\n" + usr_p).strip() if text else usr_p
            if not text:
                continue
            if len(present) > 1:
                blocks.append(f"# {entry.get('label') or k}\n\n{text}")
            else:
                blocks.append(text)
        return "\n\n---\n\n".join(blocks)

    metadata_keys = [k for k in sp if k.startswith("metadata_")]
    thumb_keys = [k for k in sp if k.startswith("thumbnail_")]
    script_keys = [k for k in sp if k.startswith("script_")]

    return {
        "research": {
            "instruction": merge_prompt("research"),
            "response": _research_response(bundle.get("research")),
        },
        "concept": {
            "instruction": merge_prompt("concept"),
            "response": _concept_response(bundle.get("concept")),
        },
        "scripts": {
            "instruction": merge_prompt(*script_keys) if script_keys else "",
            "response": _scripts_response(bundle.get("scripts") or []),
        },
        "scenes": {
            "instruction": merge_prompt("scenes"),
            "response": _scenes_response(bundle.get("scenes") or []),
        },
        "metadata": {
            "instruction": merge_prompt(*metadata_keys) if metadata_keys else "",
            "response": _metadata_response(bundle.get("metadata") or []),
        },
        "thumbnails": {
            "instruction": merge_prompt(*thumb_keys) if thumb_keys else "",
            "response": _thumbnails_response(bundle.get("thumbnails") or []),
        },
        "qc": {"instruction": "", "response": ""},
    }


def main():
    print("== Backup ==")
    backup_path = backup_db()
    print(f"  -> {backup_path.relative_to(ROOT)} ({backup_path.stat().st_size} bytes)")

    bundles: dict[int, dict] = {}
    folders: dict[int, Path] = {}
    for pid, prefix in REAL_PREFIXES.items():
        folder = find_folder(pid, prefix)
        folders[pid] = folder
        bundle_path = folder / "08_paquete_completo.json"
        bundles[pid] = json.loads(bundle_path.read_text(encoding="utf-8"))
        print(f"  loaded bundle id={pid} -> {folder.name}")

    stonehenge = bundles[15]
    rs_template: dict[str, Any] = {r["name"]: r for r in stonehenge["roadmap_stages"]}
    # Map bundle's roadmap_stage_id -> stage name (so we can remap to
    # profile 1's current rs_ids when inserting Stonehenge's project_stages).
    bundle_rsid_to_name: dict[int, str] = {
        r["id"]: r["name"] for r in stonehenge["roadmap_stages"]
    }
    stonehenge_ps = stonehenge["project_stages"]
    print(f"\n== Stonehenge roadmap template stage names: {list(rs_template.keys())} ==")

    # We do everything inside one connection/transaction for atomicity.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()

        # 1) Profile 1: rename + restore to Stonehenge values
        print("\n== Update profile 1 ==")
        prof = stonehenge["profile"]
        cur.execute(
            """
            UPDATE profiles SET
                name = ?, content_type = ?, audience = ?, tone = ?,
                style = ?, mystery_level = ?, drama_level = ?,
                narration_speed = ?, platforms = ?, notes = ?,
                is_default = 1
            WHERE id = 1
            """,
            (
                prof.get("name") or "Todo Sobre Todo / Misterio",
                prof.get("content_type"),
                prof.get("audience"),
                prof.get("tone"),
                prof.get("style"),
                prof.get("mystery_level"),
                prof.get("drama_level"),
                prof.get("narration_speed"),
                prof.get("platforms"),
                prof.get("notes") or "",
            ),
        )
        print(f"  rows updated: {cur.rowcount}")

        # 2) Delete synthetic projects 1 & 2 + their project_stages
        # (FK ON DELETE CASCADE handles project_stages; explicit delete is harmless.)
        print("\n== Delete synthetic projects 1 and 2 ==")
        cur.execute("DELETE FROM project_stages WHERE project_id IN (1, 2)")
        cur.execute("DELETE FROM projects WHERE id IN (1, 2)")
        print(f"  removed projects 1, 2 (and their project_stages)")

        # 3) Seed 7 roadmap_stages for profile_id=1.
        # IMPORTANT: preserve existing IDs 1 (research) and 2 (concept) so
        # Stonehenge's project_stages (which reference rs_id=1..7) stay
        # joined. UPDATE 1,2 in place and INSERT new rows for 3..7.
        print("\n== Seed roadmap_stages for profile_id=1 ==")
        cur.execute(
            """
            UPDATE roadmap_stages
            SET instruction=?, sort_order=0, is_active=1, updated_at=?
            WHERE id=1
            """,
            (rs_template["research"]["instruction"], now_iso()),
        )
        cur.execute(
            """
            UPDATE roadmap_stages
            SET instruction=?, sort_order=1, is_active=1, updated_at=?
            WHERE id=2
            """,
            (rs_template["concept"]["instruction"], now_iso()),
        )
        new_rs_ids: dict[str, int] = {"research": 1, "concept": 2}
        for sort_idx, name in enumerate(("scripts", "scenes", "metadata", "thumbnails", "qc"), start=2):
            r = rs_template[name]
            cur.execute(
                """
                INSERT INTO roadmap_stages
                    (profile_id, name, instruction, sort_order, is_active,
                     created_at, updated_at)
                VALUES (1, ?, ?, ?, 1, ?, ?)
                """,
                (
                    name,
                    r["instruction"],
                    sort_idx,
                    now_iso(),
                    now_iso(),
                ),
            )
            new_rs_ids[name] = cur.lastrowid or 0
        print(f"  roadmap_stage ids: {new_rs_ids}")

        # 4) Insert 6 legacy projects
        print("\n== Insert 6 legacy projects ==")
        legacy_ids = [1, 9, 11, 12, 13, 14]
        for pid in legacy_ids:
            bundle = bundles[pid]
            proj = dict(bundle["project"])
            proj["status"] = FORCED_STATUS[pid]
            cur.execute(
                """
                INSERT INTO projects (id, name, topic, profile_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    proj.get("name") or "",
                    proj.get("topic") or "",
                    1,
                    proj["status"],
                    proj.get("created_at") or now_iso(),
                    proj.get("updated_at") or now_iso(),
                ),
            )
            stage_map = build_legacy_stages(bundle)
            for stage_name in ROADMAP_ORDER:
                rs_id = new_rs_ids[stage_name]
                entry = stage_map[stage_name]
                cur.execute(
                    """
                    INSERT INTO project_stages
                        (project_id, roadmap_stage_id, instruction, response, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        pid,
                        rs_id,
                        entry["instruction"],
                        entry["response"],
                        now_iso(),
                    ),
                )
            print(f"  id={pid:2d} {proj.get('name')!r} status={proj['status']} -> 7 project_stages")

        # 5) Insert Stonehenge (id=15). The bundle's project_stages reference
        # roadmap_stage_ids from the OLD profile 1 layout (36..42). We remap
        # each row by stage name to the CURRENT profile 1 ids so the joins
        # work. Instruction and response content are taken as-is from the
        # bundle (per spec: "mantener exactamente esos valores").
        print("\n== Insert Stonehenge (id=15) ==")
        proj15 = dict(stonehenge["project"])
        proj15["status"] = FORCED_STATUS[15]
        cur.execute(
            """
            INSERT INTO projects (id, name, topic, profile_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                15,
                proj15.get("name") or "",
                proj15.get("topic") or "",
                1,
                proj15["status"],
                proj15.get("created_at") or now_iso(),
                proj15.get("updated_at") or now_iso(),
            ),
        )
        for ps in stonehenge_ps:
            stage_name = bundle_rsid_to_name.get(ps["roadmap_stage_id"])
            current_rsid = new_rs_ids.get(stage_name) if stage_name else None
            if current_rsid is None:
                raise ValueError(
                    f"Stonehenge project_stage {ps['id']} references unknown "
                    f"roadmap_stage_id={ps['roadmap_stage_id']} "
                    f"(stage_name={stage_name!r})"
                )
            cur.execute(
                """
                INSERT INTO project_stages
                    (project_id, roadmap_stage_id, instruction, response, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    15,
                    current_rsid,
                    ps.get("instruction") or "",
                    ps.get("response") or "",
                    ps.get("updated_at") or now_iso(),
                ),
            )
        print(f"  inserted Stonehenge project + {len(stonehenge_ps)} project_stages")

        # 6) profile_prompts UPSERT for profile_id=1
        print("\n== UPSERT profile_prompts for profile_id=1 ==")
        cur.execute("DELETE FROM profile_prompts WHERE profile_id=1")
        for stage_name in ROADMAP_ORDER:
            entry = rs_template[stage_name]
            cur.execute(
                """
                INSERT INTO profile_prompts
                    (profile_id, stage, sys_prompt, user_prompt, updated_at)
                VALUES (?, ?, ?, '', ?)
                """,
                (
                    1,
                    stage_name,
                    entry["instruction"],
                    now_iso(),
                ),
            )
        # Clear any stray prompts for profile 3
        cur.execute("DELETE FROM profile_prompts WHERE profile_id=3")
        print(f"  profile_prompts seeded (7 rows for profile 1)")

        conn.commit()
        print("\n== Transaction committed ==")
    except Exception:
        conn.rollback()
        print("\n!! Transaction rolled back due to error")
        raise
    finally:
        conn.close()

    # ---- Post-recovery filesystem cleanup ----------------------------------
    print("\n== Cleanup artifact folders ==")
    artifact_dirs = [
        ROOT / "projects" / "ProjA_1",
        ROOT / "projects" / "Proj_A_1",
        ROOT / "projects" / "Verificacion_pipeline_2",
        ROOT / "projects" / "Otro_Nombre_Con_Acentos_2",
    ]
    for d in artifact_dirs:
        if d.exists():
            shutil.rmtree(d)
            print(f"  removed dir: {d.relative_to(ROOT)}")
        else:
            print(f"  already absent: {d.relative_to(ROOT)}")
    zip_targets = [
        ROOT / "projects" / "ProjA_1.zip",
        ROOT / "projects" / "Proj_A_1.zip",
        ROOT / "projects" / "Verificacion_pipeline_2.zip",
    ]
    for z in zip_targets:
        if z.exists():
            z.unlink()
            print(f"  removed zip: {z.relative_to(ROOT)}")
    print("\nDone.")


if __name__ == "__main__":
    main()
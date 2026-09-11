"""De-duplicate roadmap_stages 22-26 against 3-7 and merge content.

Idempotent. If rs_id 22-26 have already been removed, this script exits
without touching the DB.

Historical context: after a couple of recovery-script runs, profile 1 ended
up with two roadmap_stage rows per stage for scripts/scenes/metadata/
thumbnails/qc (rs_id 3-7 and rs_id 22-26). Each project's project_stages
contained a row per duplicate, with response content distributed
asymmetrically across both. That broke ``project_stage_status`` (the dict
built by overwriting last-wins produced inconsistent results).

This script:
  1) For each (project_id, stage_name) where both rs_id 3-7 and rs_id 22-26
     exist, merges the longer non-empty response and instruction into the
     rs_id 3-7 row (UPDATE).
  2) Deletes the rs_id 22-26 project_stages rows.
  3) Deletes the rs_id 22-26 roadmap_stages rows.

Single transaction. On failure the DB stays untouched (a backup is created
in backups/ before any change).
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import DB_PATH, now_iso  # noqa: E402

PAIRS: tuple[tuple[str, int, int], ...] = (
    ("scripts", 3, 22),
    ("scenes", 4, 23),
    ("metadata", 5, 24),
    ("thumbnails", 6, 25),
    ("qc", 7, 26),
)

ORPHAN_RS_IDS: tuple[int, ...] = (22, 23, 24, 25, 26)


def backup_db() -> Path:
    backups = ROOT / "backups"
    backups.mkdir(exist_ok=True)
    ts = now_iso().replace(":", "-").replace(".", "-")
    target = backups / f"workflow_pre_dedup_{ts}.db"
    shutil.copy2(DB_PATH, target)
    return target


def main() -> None:
    print("== Backup ==")
    backup_path = backup_db()
    print(f"  -> {backup_path.relative_to(ROOT)} ({backup_path.stat().st_size} bytes)")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT id, profile_id, name FROM roadmap_stages WHERE id IN (?, ?, ?, ?, ?)",
            ORPHAN_RS_IDS,
        )
        orphans = [dict(r) for r in cur.fetchall()]
        if not orphans:
            print("\n== No rs_id 22-26 found; nothing to clean up ==")
            conn.commit()
            return
        profiles_touched = {r["profile_id"] for r in orphans}
        for p in profiles_touched:
            cur.execute("SELECT id, name FROM roadmap_stages WHERE profile_id=? ORDER BY id", (p,))
            print(f"  profile {p} roadmap_stages before: {[dict(r) for r in cur.fetchall()]}")

        merged = 0
        deleted_ps = 0

        cur.execute("SELECT id FROM projects")
        project_ids = [r["id"] for r in cur.fetchall()]

        for pid in project_ids:
            for _stage_name, small_id, big_id in PAIRS:
                cur.execute(
                    "SELECT id, response, instruction, updated_at "
                    "FROM project_stages WHERE project_id=? AND roadmap_stage_id=?",
                    (pid, small_id),
                )
                small = cur.fetchone()
                cur.execute(
                    "SELECT id, response, instruction, updated_at "
                    "FROM project_stages WHERE project_id=? AND roadmap_stage_id=?",
                    (pid, big_id),
                )
                big = cur.fetchone()

                if big is None:
                    continue

                if small is None:
                    cur.execute(
                        """
                        INSERT INTO project_stages
                            (project_id, roadmap_stage_id, instruction, response, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            pid,
                            small_id,
                            big["instruction"] or "",
                            big["response"] or "",
                            big["updated_at"] or now_iso(),
                        ),
                    )
                    merged += 1
                else:
                    small_resp = (small["response"] or "").strip()
                    big_resp = (big["response"] or "").strip()
                    chosen_resp = big_resp if len(big_resp) >= len(small_resp) else small_resp

                    small_instr = (small["instruction"] or "").strip()
                    big_instr = (big["instruction"] or "").strip()
                    chosen_instr = big_instr if len(big_instr) >= len(small_instr) else small_instr

                    cur.execute(
                        """
                        UPDATE project_stages
                        SET response=?, instruction=?, updated_at=?
                        WHERE id=?
                        """,
                        (chosen_resp, chosen_instr, now_iso(), small["id"]),
                    )
                    merged += 1

                cur.execute("DELETE FROM project_stages WHERE id=?", (big["id"],))
                deleted_ps += 1

        print(f"\n== Merged {merged} (project, stage) pairs ==")
        print(f"== Deleted {deleted_ps} orphan project_stages rows ==")

        cur.execute(
            f"DELETE FROM roadmap_stages WHERE id IN ({','.join('?' * len(ORPHAN_RS_IDS))})",
            ORPHAN_RS_IDS,
        )
        print(f"== Deleted {cur.rowcount} orphan roadmap_stages rows ==")

        for p in profiles_touched:
            cur.execute("SELECT id, name, sort_order, is_active FROM roadmap_stages WHERE profile_id=? ORDER BY sort_order", (p,))
            print(f"  profile {p} roadmap_stages after: {[dict(r) for r in cur.fetchall()]}")

        conn.commit()
        print("\n== Transaction committed ==")
    except Exception:
        conn.rollback()
        print("\n!! Transaction rolled back due to error")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

"""Sincronización de la carpeta del proyecto en disco.

Funciones puras (no acceden a ``flask.request`` ni ``flask.session``):

- ``safe_project_dir(project_id, name)``: ruta canónica sanitizada.
- ``delete_project_folder(project_id, name)``: borrado idempotente.
- ``sync_project_folder(project_id)``: reconstruye la carpeta del proyecto
  a partir de la BD. Devuelve ``(carpeta, [rutas_relativas])``.

Para evitar ciclos con ``app.py`` (T2.1) las dependencias de Flask
(``get_db``, ``PROJECTS_DIR``, helpers de BD como ``get_profile`` /
``fetch_optional_dict``) se importan localmente dentro de cada función.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


def safe_project_dir(project_id: int, name: str) -> Path:
    """Devuelve la ruta canónica de la carpeta del proyecto en ``PROJECTS_DIR``.

    El nombre se sanitiza para que sea seguro en sistemas de archivos y se le
    añade el id (único) para evitar colisiones entre proyectos con el mismo
    nombre.
    """
    from app import PROJECTS_DIR

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
    # Import local para evitar ciclo: app.py -> services.sync -> app.
    from app import (
        PROJECTS_DIR,
        fetch_optional_dict,
        get_db,
        get_profile,
        list_profile_prompts,
        now_iso,
    )

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
            f.write(f"## Ángulo\n{concept_obj.get('angle','')}\n\n")
            f.write(f"## Tesis\n{concept_obj.get('thesis','')}\n\n")
            kp = json.loads(concept_obj.get("key_points") or "[]")
            if kp:
                f.write("## Puntos clave\n\n")
                for i, p in enumerate(kp, 1):
                    f.write(f"{i}. {p}\n")
                f.write("\n")
            if concept_obj.get("emotional_hook"):
                f.write(f"## Gancho emocional\n{concept_obj['emotional_hook']}\n\n")
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
                    f.write(f"## Hook\n{s['hook']}\n\n")
                if s.get("context"):
                    f.write(f"## Contexto\n{s['context']}\n\n")
                if s.get("development"):
                    f.write(f"## Desarrollo\n{s['development']}\n\n")
                if s.get("revelations"):
                    f.write(f"## Revelaciones\n{s['revelations']}\n\n")
                if s.get("conclusion"):
                    f.write(f"## Conclusión\n{s['conclusion']}\n\n")
                if s.get("cta"):
                    f.write(f"## CTA\n{s['cta']}\n\n")
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
                    f.write(f"## Descripción\n{m['description']}\n\n")
                chapters = json.loads(m.get("chapters") or "[]")
                if chapters:
                    f.write("## Capítulos\n\n")
                    for c in chapters:
                        f.write(f"{c}\n")
                    f.write("\n")
                tags = json.loads(m.get("tags") or "[]")
                if tags:
                    f.write(f"## Tags\n{', '.join(tags)}\n\n")
                hashtags = json.loads(m.get("hashtags") or "[]")
                if hashtags:
                    f.write(f"## Hashtags\n{' '.join(hashtags)}\n\n")
                if m.get("caption"):
                    f.write(f"## Caption\n{m['caption']}\n\n")
                if m.get("hook"):
                    f.write(f"## Hook\n{m['hook']}\n\n")
                if m.get("cta"):
                    f.write(f"## CTA\n{m['cta']}\n\n")
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
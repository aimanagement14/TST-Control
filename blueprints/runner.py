"""Blueprint `runner`: ejecucion nodo a nodo sobre un proyecto.

Rutas:
- GET  /projects/<id>/run                — render del runner.
- POST /projects/<id>/run/execute        — ejecuta un nodo.
- POST /projects/<id>/run/reset-node     — resetea el output de un nodo.

Misma convencion que blueprints/graph.py: las funciones de dominio
se importan con local import dentro de cada handler para evitar
ciclos con app.py.
"""

from __future__ import annotations

import json

from flask import Blueprint, abort, jsonify, render_template, request, url_for

runner_bp = Blueprint("runner", __name__, url_prefix="/projects")


@runner_bp.route("/<int:project_id>/run", methods=["GET"])
def project_run(project_id: int):
    from app import (
        fetch_graph_edges_as_eedges,
        fetch_graph_nodes,
        fetch_project_or_404,
        get_db,
        get_default_profile,
        get_or_create_fixed_graph_nodes,
        get_profile,
    )

    project = fetch_project_or_404(project_id)
    profile = get_profile(project["profile_id"]) or get_default_profile()
    if not profile:
        abort(404)
    get_or_create_fixed_graph_nodes(profile["id"])
    nodes_rows = fetch_graph_nodes(profile["id"])
    with get_db() as conn:
        exec_rows = [dict(r) for r in conn.execute(
            "SELECT node_key, output, status, duration_ms, created_at "
            "FROM node_executions WHERE project_id=? ORDER BY id DESC",
            (project_id,),
        ).fetchall()]
    latest_by_node: dict[str, dict] = {}
    for r in exec_rows:
        latest_by_node.setdefault(r["node_key"], r)
    graph_data = {
        "mode": "runner",
        "profileId": profile["id"],
        "profileName": profile["name"],
        "projectId": project["id"],
        "projectName": project["name"],
        "executeUrl": url_for("runner.execute_graph_node_route", project_id=project["id"]),
        "resetUrl": url_for("runner.reset_graph_node_route", project_id=project["id"]),
        "nodes": [
            {
                "id": n["node_key"],
                "key": n["node_key"],
                "label": n["label"] or n["node_key"],
                "sysPrompt": n["sys_prompt"] or "",
                "userPrompt": n["user_prompt"] or "",
                "position": {"x": n["position_x"], "y": n["position_y"]},
                "isFixed": bool(n["is_fixed"]),
                "inputs": json.loads(n["inputs_json"] or "[]"),
                "status": (
                    latest_by_node[n["node_key"]]["status"]
                    if n["node_key"] in latest_by_node else "idle"
                ),
                "lastOutput": (
                    latest_by_node[n["node_key"]]["output"]
                    if n["node_key"] in latest_by_node else ""
                ),
                "durationMs": (
                    latest_by_node[n["node_key"]]["duration_ms"]
                    if n["node_key"] in latest_by_node else None
                ),
                "lastRunAt": (
                    latest_by_node[n["node_key"]]["created_at"]
                    if n["node_key"] in latest_by_node else None
                ),
            }
            for n in nodes_rows
        ],
        "edges": fetch_graph_edges_as_eedges(profile["id"]),
    }
    return render_template("project_run.html", project=project, profile=profile, graph_data=graph_data)


@runner_bp.route("/<int:project_id>/run/execute", methods=["POST"])
def execute_graph_node_route(project_id: int):
    from app import execute_graph_node, fetch_project_or_404

    fetch_project_or_404(project_id)
    body = request.get_json(silent=True) or {}
    node_key = body.get("node_key")
    if not node_key:
        abort(400)
    result = execute_graph_node(project_id, str(node_key))
    return jsonify(result)


@runner_bp.route("/<int:project_id>/run/reset-node", methods=["POST"])
def reset_graph_node_route(project_id: int):
    from app import fetch_project_or_404, get_db

    fetch_project_or_404(project_id)
    body = request.get_json(silent=True) or {}
    node_key = body.get("node_key")
    if not node_key:
        abort(400)
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM node_executions WHERE project_id=? AND node_key=?",
            (project_id, str(node_key)),
        )
    return jsonify({"ok": True, "deleted": cur.rowcount})

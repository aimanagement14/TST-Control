"""Blueprint `graph`: editor visual de grafo por perfil.

Rutas:
- GET  /profiles/<id>/graph           — render del editor.
- POST /profiles/<id>/graph/save-node  — alta/edicion de un nodo.
- POST /profiles/<id>/graph/delete-node — borrar un nodo custom.
- POST /profiles/<id>/graph/layout     — persistir posiciones.

Las funciones de dominio (CRUD de nodos, fetch de edges) viven en
app.py. Se importan con local import dentro de cada handler para
evitar ciclos: app.py importa este modulo via register_blueprint,
asi que el top-level de este archivo no puede depender de app.
"""

from __future__ import annotations

import json

from flask import Blueprint, abort, jsonify, render_template, request, url_for

graph_bp = Blueprint("graph", __name__, url_prefix="/profiles")


@graph_bp.route("/<int:profile_id>/graph", methods=["GET"])
def profile_graph(profile_id: int):
    from app import (
        fetch_graph_edges_as_eedges,
        fetch_graph_nodes,
        get_or_create_fixed_graph_nodes,
        get_profile,
    )

    profile = get_profile(profile_id)
    if not profile:
        abort(404)
    get_or_create_fixed_graph_nodes(profile_id)
    nodes_rows = fetch_graph_nodes(profile_id)
    graph_data = {
        "mode": "editor",
        "profileId": profile["id"],
        "profileName": profile["name"],
        "saveUrl": url_for("graph.save_graph_node_route", profile_id=profile["id"]),
        "deleteUrl": url_for("graph.delete_graph_node_route", profile_id=profile["id"]),
        "layoutUrl": url_for("graph.save_graph_layout", profile_id=profile["id"]),
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
                "status": "idle",
            }
            for n in nodes_rows
        ],
        "edges": fetch_graph_edges_as_eedges(profile_id),
    }
    return render_template("profile_graph.html", profile=profile, graph_data=graph_data)


@graph_bp.route("/<int:profile_id>/graph/save-node", methods=["POST"])
def save_graph_node_route(profile_id: int):
    from app import (
        KNOWN_FIXED_NODE_KEYS,
        get_profile,
        save_graph_node,
    )

    if not get_profile(profile_id):
        abort(404)
    body = request.get_json(silent=True) or {}
    node_key = body.get("node_key")
    if not node_key:
        abort(400)
    label = (body.get("label") or node_key) or ""
    sys_prompt = body.get("sys_prompt") or ""
    user_prompt = body.get("user_prompt") or ""
    inputs = body.get("inputs") or []
    if not isinstance(inputs, list):
        abort(400)
    pos = body.get("position") or {}
    is_fixed = bool(body.get("is_fixed", node_key in KNOWN_FIXED_NODE_KEYS))
    node = save_graph_node(
        profile_id,
        str(node_key),
        str(label),
        str(sys_prompt),
        str(user_prompt),
        json.dumps(inputs, ensure_ascii=False),
        float(pos.get("x", 0) or 0),
        float(pos.get("y", 0) or 0),
        is_fixed,
    )
    return jsonify({"ok": True, "node": node})


@graph_bp.route("/<int:profile_id>/graph/delete-node", methods=["POST"])
def delete_graph_node_route(profile_id: int):
    from app import delete_graph_node, get_profile

    if not get_profile(profile_id):
        abort(404)
    body = request.get_json(silent=True) or {}
    node_key = body.get("node_key")
    if not node_key:
        abort(400)
    deleted = delete_graph_node(profile_id, str(node_key))
    return jsonify({"ok": True, "deleted": deleted})


@graph_bp.route("/<int:profile_id>/graph/layout", methods=["POST"])
def save_graph_layout(profile_id: int):
    from app import get_profile, update_graph_layout

    if not get_profile(profile_id):
        abort(404)
    body = request.get_json(silent=True) or {}
    nodes_data = body.get("nodes") or []
    if not isinstance(nodes_data, list):
        abort(400)
    updated = update_graph_layout(profile_id, nodes_data)
    return jsonify({"ok": True, "updated": updated})

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file
from werkzeug.utils import secure_filename

from .module2_graph import GraphService
from .auth import require_auth
from .module2_store import (
    Module2Error,
    ValidationError,
    close_connection,
    create_edge,
    create_node,
    delete_edge,
    delete_node,
    get_connection,
    get_edge,
    get_layout_asset,
    get_layout_path,
    get_node,
    list_edges,
    list_nodes,
    replace_graph,
    save_layout_asset,
    update_edge,
    update_node,
)

module2_bp = Blueprint("module2", __name__)
module2_bp.teardown_app_request(close_connection)


@module2_bp.errorhandler(Module2Error)
def handle_module2_error(error: Module2Error):
    return jsonify({"error": str(error)}), error.status_code


@module2_bp.errorhandler(ValueError)
def handle_value_error(error: ValueError):
    return jsonify({"error": str(error)}), 422


@module2_bp.get("/")
def get_module2():
    return jsonify(
        {
            "module": "module2",
            "purpose": "Cable layout digitization and graph engine",
            "status": "ready",
        }
    )


@module2_bp.post("/nodes")
@require_auth(role="engineer")
def post_node():
    node = create_node(get_connection(), request.get_json(force=True, silent=False) or {})
    return jsonify(node), 201


@module2_bp.get("/nodes")
def get_nodes():
    return jsonify({"nodes": list_nodes(get_connection())})


@module2_bp.get("/nodes/<node_id>")
def get_node_by_id(node_id: str):
    return jsonify(get_node(get_connection(), node_id))


@module2_bp.put("/nodes/<node_id>")
@require_auth(role="engineer")
def put_node(node_id: str):
    node = update_node(get_connection(), node_id, request.get_json(force=True, silent=False) or {})
    return jsonify(node)


@module2_bp.delete("/nodes/<node_id>")
@require_auth(role="engineer")
def remove_node(node_id: str):
    delete_node(get_connection(), node_id)
    return "", 204


@module2_bp.post("/edges")
@require_auth(role="engineer")
def post_edge():
    edge = create_edge(get_connection(), request.get_json(force=True, silent=False) or {})
    return jsonify(edge), 201


@module2_bp.get("/edges")
def get_edges():
    return jsonify({"edges": list_edges(get_connection())})


@module2_bp.get("/edges/<edge_id>")
def get_edge_by_id(edge_id: str):
    return jsonify(get_edge(get_connection(), edge_id))


@module2_bp.put("/edges/<edge_id>")
@require_auth(role="engineer")
def put_edge(edge_id: str):
    edge = update_edge(get_connection(), edge_id, request.get_json(force=True, silent=False) or {})
    return jsonify(edge)


@module2_bp.delete("/edges/<edge_id>")
@require_auth(role="engineer")
def remove_edge(edge_id: str):
    delete_edge(get_connection(), edge_id)
    return "", 204


@module2_bp.get("/graph")
def get_graph():
    return jsonify(GraphService(get_connection()).get_graph())


@module2_bp.get("/graph/validate")
def validate_graph():
    return jsonify(GraphService(get_connection()).validate_graph())


@module2_bp.get("/graph/nearest")
def get_nearest_position():
    source_node_id = request.args.get("source_node_id", "").strip()
    if not source_node_id:
        raise ValidationError("source_node_id is required.")
    try:
        distance_m = float(request.args.get("distance_m", ""))
    except ValueError as exc:
        raise ValidationError("distance_m must be a valid number.") from exc
    return jsonify(
        GraphService(get_connection()).get_nearest_position(
            source_node_id=source_node_id,
            distance_m=distance_m,
        )
    )


@module2_bp.get("/graph/export")
def export_graph():
    return jsonify(GraphService(get_connection()).export_graph())


@module2_bp.post("/graph/import")
@require_auth(role="admin")
def import_graph():
    replace_graph(get_connection(), request.get_json(force=True, silent=False) or {})
    return jsonify(GraphService(get_connection()).get_graph()), 201


@module2_bp.get("/layout-image")
def get_layout_image():
    asset = get_layout_asset()
    if asset is None:
        return jsonify({"layout_image_url": None, "uploaded_at": None})
    image_path = get_layout_path(asset["filename"])
    if not image_path.exists():
        return jsonify({"layout_image_url": None, "uploaded_at": asset["uploaded_at"]})
    return jsonify(
        {
            "layout_image_url": f"/api/module2/layout-image/file/{asset['filename']}",
            "uploaded_at": asset["uploaded_at"],
        }
    )


@module2_bp.get("/layout-image/file/<path:filename>")
def get_layout_image_file(filename: str):
    image_path = get_layout_path(filename)
    if not image_path.exists():
        raise Module2Error("Layout image file was not found.", status_code=404)
    return send_file(image_path)


@module2_bp.post("/layout-image")
@require_auth(role="admin")
def upload_layout_image():
    if "file" not in request.files:
        raise ValidationError("A layout image file is required.")

    file = request.files["file"]
    if not file.filename:
        raise ValidationError("A layout image file is required.")

    safe_name = secure_filename(file.filename)
    if not safe_name:
        raise ValidationError("The uploaded file name is invalid.")

    layout_dir = Path(current_app.config["MODULE2_LAYOUT_DIR"])
    layout_dir.mkdir(parents=True, exist_ok=True)
    filename = f"layout{Path(safe_name).suffix.lower()}"
    file_path = layout_dir / filename
    file.save(file_path)
    save_layout_asset(filename)

    return jsonify(
        {
            "layout_image_url": f"/api/module2/layout-image/file/{filename}",
            "uploaded_at": get_layout_asset()["uploaded_at"],
        }
    ), 201

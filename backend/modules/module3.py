from flask import Blueprint, jsonify

module3_bp = Blueprint("module3", __name__)


@module3_bp.get("/")
def get_module3():
    return jsonify(
        {
            "module": "module3",
            "purpose": "Historical diagnostics and logs",
            "status": "ready",
        }
    )

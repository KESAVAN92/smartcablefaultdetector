from flask import Blueprint, jsonify

module2_bp = Blueprint("module2", __name__)


@module2_bp.get("/")
def get_module2():
    return jsonify(
        {
            "module": "module2",
            "purpose": "Fault detection workflow",
            "status": "ready",
        }
    )

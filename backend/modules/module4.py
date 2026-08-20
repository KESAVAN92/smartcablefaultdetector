from flask import Blueprint, jsonify

module4_bp = Blueprint("module4", __name__)


@module4_bp.get("/")
def get_module4():
    return jsonify(
        {
            "module": "module4",
            "purpose": "Reporting and exports",
            "status": "ready",
        }
    )

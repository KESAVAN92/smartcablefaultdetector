from flask import Blueprint, jsonify

module1_bp = Blueprint("module1", __name__)


@module1_bp.get("/")
def get_module1():
    return jsonify(
        {
            "module": "module1",
            "purpose": "Cable registration and metadata",
            "status": "ready",
        }
    )

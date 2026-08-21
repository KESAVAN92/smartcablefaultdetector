"""
Cable Fault Detector — Flask application entry point.

Module ownership:
  module1_bp  → /api/module1   (Module 1 team — fault simulation engine)
  module2_bp  → /api/module2   (Module 2 team — graph engine)
  module3_bp  → /api/module3   (Module 3 team — fault mapping & live map)
  module4_bp  → /api/module4   (Module 4 team — reporting & exports)

SocketIO namespaces (registered by Module 3):
  /readings      — raw sensor readings stream
  /fault-events  — live fault event stream
"""

import os
from pathlib import Path

import eventlet
eventlet.monkey_patch()

from flask import Flask, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO

from modules.module1 import (
    create_reading,
    get_module1,
    init_module1,
    inject_fault,
    list_readings,
    module1_bp,
)
from modules.module2 import module2_bp
from modules.module4 import module4_bp

from database import init_db

# SocketIO singleton — shared between routes and background tasks
socketio = SocketIO()


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": "*"}})

    base_dir = Path(__file__).resolve().parent
    app.config.update(
        DATABASE_PATH=str(base_dir / "data" / "module2.sqlite3"),
        MODULE2_LAYOUT_DIR=str(base_dir / "storage" / "module2"),
        ML_DATASET_PATH=str(base_dir.parent / "underground_cable_ml_dataset_30000 (8).csv"),
        ML_MODEL_VERSION="ml-demo-2026.08",
        ML_UNKNOWN_CONFIDENCE_THRESHOLD=0.50,
    )
    if test_config:
        app.config.update(test_config)
    app.config.setdefault(
        "ML_ENABLE_ASYNC_PREDICTIONS",
        not app.config.get("TESTING", False),
    )
    app.config.setdefault(
        "MODULE3_START_BACKGROUND",
        os.environ.get("MODULE3_START_BACKGROUND", "1") == "1"
        and not app.config.get("TESTING", False),
    )

    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["MODULE2_LAYOUT_DIR"]).mkdir(parents=True, exist_ok=True)

    @app.get("/")
    def index():
        return jsonify(
            {
                "service": "cablefaultdetector-backend",
                "status": "ok",
                "routes": {
                    "health": "/api/health",
                    "module1_info": "/api/module1/",
                    "module1_calculate": "/api/module1/calculate",
                    "inject_fault": "/simulate/inject-fault",
                    "readings": "/readings",
                    "readings_stream": "/readings/stream",
                },
            }
        )

    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="eventlet",
        logger=False,
        engineio_logger=False,
    )

    # ── Database ───────────────────────────────────────────────────────────────
    # Creates only the tables Module 3 owns (fault_events).
    # M1/M2 will call their own init_db() when they push their branches.
    init_db()

    # ── Blueprints ─────────────────────────────────────────────────────────────
    app.register_blueprint(module1_bp, url_prefix="/api/module1")
    app.register_blueprint(module2_bp, url_prefix="/api/module2")
    app.register_blueprint(module4_bp, url_prefix="/api/module4")

    # Module 3 is now a package — import and register its blueprint
    from modules.module3 import module3_bp, init_module3
    app.register_blueprint(module3_bp, url_prefix="/api/module3")

    # Wire Module 3's services (mapping service + M1 adapter background thread)
    init_module3(socketio, start_background=app.config["MODULE3_START_BACKGROUND"])

    init_module1(app)

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/api/health")
    def health_check():
        return jsonify({"status": "ok", "service": "cablefaultdetector-backend"})

    # Initialize module4 (alerts, auth, reports)
    try:
        from modules.module4 import init_module4

        init_module4(app)
    except Exception:
        # If module4 fails to initialize, continue without blocking the app startup.
        pass
    from ml.api import ml_bp
    from ml.prediction_service import PredictionService

    app.extensions["ml_prediction_service"] = PredictionService(app)
    app.register_blueprint(ml_bp)
    # Exact contract aliases for downstream consumers.
    app.add_url_rule("/readings", "module1_readings_post", create_reading, methods=["POST"])
    app.add_url_rule("/readings", "module1_readings_get", list_readings, methods=["GET"])
    app.add_url_rule("/simulate/inject-fault", "module1_inject_fault", inject_fault, methods=["POST"])
    app.add_url_rule("/simulate/info", "module1_info_alias", get_module1, methods=["GET"])

    return app


app = create_app(
    {
        "MODULE1_START_BACKGROUND": os.environ.get("MODULE1_START_BACKGROUND", "1") == "1",
        "MODULE3_START_BACKGROUND": os.environ.get("MODULE3_START_BACKGROUND", "1") == "1",
    }
)


if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)

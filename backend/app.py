import os
from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS

from modules.module1 import (
    create_reading,
    get_module1,
    init_module1,
    inject_fault,
    list_readings,
    module1_bp,
)
from modules.module2 import module2_bp
from modules.module3 import module3_bp
from modules.module4 import module4_bp


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app)
    if test_config:
        app.config.update(test_config)

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

    base_dir = Path(__file__).resolve().parent
    app.config.update(
        DATABASE_PATH=str(base_dir / "data" / "module2.sqlite3"),
        MODULE2_LAYOUT_DIR=str(base_dir / "storage" / "module2"),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["MODULE2_LAYOUT_DIR"]).mkdir(parents=True, exist_ok=True)

    @app.get("/api/health")
    def health_check():
        return jsonify({"status": "ok", "service": "cablefaultdetector-backend"})

    app.register_blueprint(module1_bp, url_prefix="/api/module1")
    app.register_blueprint(module2_bp, url_prefix="/api/module2")
    app.register_blueprint(module3_bp, url_prefix="/api/module3")
    app.register_blueprint(module4_bp, url_prefix="/api/module4")
    init_module1(app)

    # Exact contract aliases for downstream consumers.
    app.add_url_rule("/readings", "module1_readings_post", create_reading, methods=["POST"])
    app.add_url_rule("/readings", "module1_readings_get", list_readings, methods=["GET"])
    app.add_url_rule("/simulate/inject-fault", "module1_inject_fault", inject_fault, methods=["POST"])
    app.add_url_rule("/simulate/info", "module1_info_alias", get_module1, methods=["GET"])

    return app


app = create_app(
    {
        "MODULE1_START_BACKGROUND": os.environ.get("MODULE1_START_BACKGROUND", "1") == "1",
    }
)


if __name__ == "__main__":
    app.run(debug=True)

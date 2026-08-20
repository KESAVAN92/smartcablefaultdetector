from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS

from modules.module1 import module1_bp
from modules.module2 import module2_bp
from modules.module3 import module3_bp
from modules.module4 import module4_bp


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app)

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

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)

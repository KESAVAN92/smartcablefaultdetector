from flask import Flask, jsonify
from flask_cors import CORS

from modules.module1 import module1_bp
from modules.module2 import module2_bp
from modules.module3 import module3_bp
from modules.module4 import module4_bp


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

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

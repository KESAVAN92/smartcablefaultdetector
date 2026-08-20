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

import eventlet
eventlet.monkey_patch()

from flask import Flask, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO

from modules.module1 import module1_bp
from modules.module2 import module2_bp
from modules.module4 import module4_bp

from database import init_db

# SocketIO singleton — shared between routes and background tasks
socketio = SocketIO()


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": "*"}})

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
    init_module3(socketio)

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/api/health")
    def health_check():
        return jsonify({"status": "ok", "service": "cablefaultdetector-backend"})

    return app


app = create_app()


if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)

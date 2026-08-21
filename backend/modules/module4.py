import os
import sqlite3
import threading
import queue
import json
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, current_app, jsonify, request, g, send_file
from flask_sock import Sock
from werkzeug.security import generate_password_hash, check_password_hash
from .auth import create_jwt, decode_jwt, require_auth

module4_bp = Blueprint("module4", __name__)
sock = Sock()

# Websocket subscribers for alert broadcasts
_alert_subscribers: list[queue.Queue] = []
_alert_lock = threading.Lock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    if "module4_db" not in g:
        database_path = current_app.config["DATABASE_PATH"]
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        g.module4_db = connection
        _ensure_schema(connection)
    return g.module4_db


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','engineer')),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fault_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reading_id INTEGER,
            distance_m REAL,
            is_overload INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            acknowledged_by TEXT,
            resolved_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fault_event_id INTEGER,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    connection.commit()


class AuthError(Exception):
    pass


def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET") or current_app.config.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT secret is not configured. Set JWT_SECRET in environment or app config.")
    return secret


# use auth helpers from modules.auth


def init_module4(app):
    sock.init_app(app)

    @sock.route("/alerts/stream")
    def alerts_stream(ws):
        # simple broadcast queue per connection
        subscriber = queue.Queue()
        with _alert_lock:
            _alert_subscribers.append(subscriber)

        try:
            while True:
                try:
                    payload = subscriber.get(timeout=1)
                except queue.Empty:
                    # allow client to send pings or disconnect
                    ping = ws.receive()
                    if ping is None:
                        break
                    continue
                try:
                    ws.send(json.dumps(payload))
                except Exception:
                    break
        except Exception:
            pass
        finally:
            with _alert_lock:
                if subscriber in _alert_subscribers:
                    _alert_subscribers.remove(subscriber)

    return None


def handle_new_reading(reading: dict[str, Any]):
    # Called by module1 when a new reading is persisted.
    try:
        connection = get_connection()
    except RuntimeError:
        # DB not available (app not fully initialized)
        return

    is_overload = 1 if reading.get("is_overload") else 0
    distance_m = reading.get("distance_m")
    created_at = reading.get("recorded_at") or utc_now_iso()
    cursor = connection.execute(
        "INSERT INTO fault_events (reading_id, distance_m, is_overload, created_at) VALUES (?, ?, ?, ?)",
        (reading.get("id"), distance_m, is_overload, created_at),
    )
    connection.commit()
    event_id = cursor.lastrowid

    # Create an alert row
    alert_type = "overload" if is_overload else "fault"
    message = f"{alert_type} detected at source {reading.get('source_node_id')}"
    connection.execute(
        "INSERT INTO alerts (fault_event_id, type, message, created_at) VALUES (?, ?, ?, ?)",
        (event_id, alert_type, message, utc_now_iso()),
    )
    connection.commit()

    # Broadcast a minimal notification on /alerts/stream using the app's test client to reach websocket
    # For simplicity, write to a lightweight in-memory notification store on the app object
    try:
        app = current_app._get_current_object()
        app.notifications = getattr(app, "notifications", []) + [
            {"event_id": event_id, "type": alert_type, "message": message, "created_at": utc_now_iso()}
        ]
    except RuntimeError:
        # not in app context
        pass
    # Broadcast to websocket subscribers (best-effort)
    payload = {"event_id": event_id, "type": alert_type, "message": message, "created_at": utc_now_iso()}
    with _alert_lock:
        subs = list(_alert_subscribers)
    for q in subs:
        try:
            q.put(payload, block=False)
        except Exception:
            pass


@module4_bp.get("/")
def get_module4():
    return jsonify({"module": "module4", "purpose": "Reporting and exports", "status": "ready"})


@module4_bp.post("/auth/register")
def auth_register():
    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 422
    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password")
    role = payload.get("role", "engineer")
    if role not in {"admin", "engineer"}:
        return jsonify({"error": "Invalid role"}), 422
    if not email or not password:
        return jsonify({"error": "email and password are required"}), 422

    conn = get_connection()
    cur = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()
    existing = cur["c"] if cur else 0

    # If users exist, only admin may create new users
    if existing > 0 and not current_app.config.get("ENABLE_AUTH", False):
        # If auth disabled, allow open registration (test/dev convenience)
        pass
    elif existing > 0:
        # enforce admin-only registration
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "admin credentials required"}), 401
        token = auth[len("Bearer "):]
        try:
            payload = decode_jwt(token)
        except Exception:
            return jsonify({"error": "invalid token"}), 401
        if payload.get("role") != "admin":
            return jsonify({"error": "admin role required"}), 403

    password_hash = generate_password_hash(password)
    created_at = utc_now_iso()
    try:
        conn.execute(
            "INSERT INTO users (email, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (email, password_hash, role, created_at),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "email already exists"}), 409
    return jsonify({"email": email, "role": role, "created_at": created_at}), 201


@module4_bp.post("/auth/login")
def auth_login():
    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 422
    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password")
    if not email or not password:
        return jsonify({"error": "email and password are required"}), 422
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "invalid credentials"}), 401
    token = create_jwt({"email": row["email"], "role": row["role"]})
    return jsonify({"access_token": token, "role": row["role"]})


@module4_bp.post("/auth/refresh")
def auth_refresh():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Missing token"}), 401
    token = auth[len("Bearer "):]
    try:
        payload = decode_jwt(token)
    except Exception:
        return jsonify({"error": "invalid token"}), 401
    new = create_jwt({"email": payload.get("email"), "role": payload.get("role")})
    return jsonify({"access_token": new})


@module4_bp.post("/fault-events/<int:event_id>/acknowledge")
@require_auth(role="engineer")
def acknowledge_event(event_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM fault_events WHERE id = ?", (event_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    acknowledged_by = request.environ.get("auth.user")
    conn.execute(
        "UPDATE fault_events SET status = 'acknowledged', acknowledged_by = ? WHERE id = ?",
        (acknowledged_by, event_id),
    )
    conn.commit()
    return jsonify({"id": event_id, "status": "acknowledged", "acknowledged_by": acknowledged_by})


@module4_bp.post("/fault-events/<int:event_id>/resolve")
@require_auth(role="engineer")
def resolve_event(event_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM fault_events WHERE id = ?", (event_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    resolved_at = utc_now_iso()
    conn.execute(
        "UPDATE fault_events SET status = 'resolved', resolved_at = ? WHERE id = ?",
        (resolved_at, event_id),
    )
    conn.commit()
    return jsonify({"id": event_id, "status": "resolved", "resolved_at": resolved_at})


@module4_bp.get("/reports/fault-history")
def report_fault_history():
    # filters: start, end, node_id, is_overload
    start = request.args.get("start")
    end = request.args.get("end")
    node_id = request.args.get("node_id")
    is_overload = request.args.get("is_overload")
    query = "SELECT fe.*, a.message FROM fault_events fe LEFT JOIN alerts a ON a.fault_event_id = fe.id WHERE 1=1"
    params: list[Any] = []
    if start:
        query += " AND datetime(fe.created_at) >= datetime(?)"
        params.append(start)
    if end:
        query += " AND datetime(fe.created_at) <= datetime(?)"
        params.append(end)
    if is_overload is not None:
        try:
            ov = 1 if str(is_overload) in ("1", "true", "True") else 0
        except Exception:
            ov = None
        if ov is not None:
            query += " AND fe.is_overload = ?"
            params.append(ov)
    # node_id filtering is best-effort via alerts message text (simple) because readings are in separate DB
    if node_id:
        query += " AND a.message LIKE ?"
        params.append(f"%{node_id}%")
    query += " ORDER BY datetime(fe.created_at) DESC"
    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    items = [dict(r) for r in rows]
    if request.args.get("format") == "csv":
        import io, csv

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "reading_id", "distance_m", "is_overload", "status", "acknowledged_by", "resolved_at", "created_at", "message"])
        for it in items:
            writer.writerow([
                it.get("id"),
                it.get("reading_id"),
                it.get("distance_m"),
                it.get("is_overload"),
                it.get("status"),
                it.get("acknowledged_by"),
                it.get("resolved_at"),
                it.get("created_at"),
                it.get("message"),
            ])
        return (buf.getvalue(), 200, {"Content-Type": "text/csv"})
    return jsonify({"items": items})


@module4_bp.get("/reports/stats")
def report_stats():
    # basic stats: faults per day, most-faulted edge (best-effort)
    conn = get_connection()
    rows = conn.execute(
        "SELECT substr(created_at,1,10) as day, COUNT(*) as cnt FROM fault_events GROUP BY day ORDER BY day DESC"
    ).fetchall()
    per_day = [{"day": r["day"], "count": r["cnt"]} for r in rows]
    # most-faulted edge is not available without richer linking; return most recent alert type count
    rows2 = conn.execute("SELECT type, COUNT(*) as c FROM alerts GROUP BY type ORDER BY c DESC").fetchall()
    top = rows2[0]["type"] if rows2 else None
    return jsonify({"faults_per_day": per_day, "top_alert_type": top})

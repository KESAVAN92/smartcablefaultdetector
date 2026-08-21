from __future__ import annotations

import sqlite3
from flask import Blueprint, current_app, jsonify, request

from .feature_engineering import build_live_row
from .prediction_service import ensure_prediction_schema

ml_bp = Blueprint("ml", __name__)


def _connection():
    connection = sqlite3.connect(current_app.config["DATABASE_PATH"])
    connection.row_factory = sqlite3.Row
    ensure_prediction_schema(connection)
    return connection


def _service():
    return current_app.extensions["ml_prediction_service"]


@ml_bp.post("/predict")
def predict():
    payload = request.get_json(silent=True) or {}
    reading_id = payload.get("reading_id")
    if reading_id is None:
        return jsonify({"error": "reading_id is required"}), 422
    connection = sqlite3.connect(current_app.config["MODULE1_DB_PATH"])
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute("SELECT * FROM fault_readings WHERE id = ?", (reading_id,)).fetchone()
    finally:
        connection.close()
    if row is None:
        return jsonify({"error": "reading not found"}), 404
    try:
        return jsonify(_service().predict(dict(row)))
    except RuntimeError as exc:
        return jsonify({"error": "ML prediction unavailable", "reason": str(exc)}), 503


@ml_bp.get("/predictions")
def predictions():
    connection = _connection()
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
        rows = connection.execute("SELECT * FROM ml_predictions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return jsonify({"items": [dict(row) for row in rows]})
    finally:
        connection.close()


@ml_bp.get("/predictions/<int:prediction_id>")
def prediction(prediction_id):
    connection = _connection()
    try:
        row = connection.execute("SELECT * FROM ml_predictions WHERE id = ?", (prediction_id,)).fetchone()
        if row is None:
            return jsonify({"error": "prediction not found"}), 404
        return jsonify(dict(row))
    finally:
        connection.close()


@ml_bp.get("/cable/<edge_id>/health")
def cable_health(edge_id):
    connection = _connection()
    try:
        row = connection.execute("SELECT * FROM ml_predictions WHERE edge_id = ? ORDER BY id DESC LIMIT 1", (edge_id,)).fetchone()
        return jsonify(dict(row) if row else {"edge_id": edge_id, "status": "no predictions"})
    finally:
        connection.close()


@ml_bp.get("/cable/<edge_id>/history")
def cable_history(edge_id):
    connection = _connection()
    try:
        rows = connection.execute("SELECT * FROM ml_predictions WHERE edge_id = ? ORDER BY id DESC", (edge_id,)).fetchall()
        return jsonify({"items": [dict(row) for row in rows]})
    finally:
        connection.close()


@ml_bp.get("/analytics")
def analytics():
    connection = _connection()
    try:
        rows = [dict(row) for row in connection.execute("SELECT * FROM ml_predictions ORDER BY id DESC").fetchall()]
        counts = {}
        for row in rows:
            counts[row["predicted_fault_type"]] = counts.get(row["predicted_fault_type"], 0) + 1
        return jsonify({"total_predictions": len(rows), "known_faults": sum(value for key, value in counts.items() if key != "NORMAL"),
                        "unknown_anomalies": sum(row["is_anomaly"] for row in rows), "fault_distribution": counts,
                        "average_health": round(sum(row["health_score"] for row in rows) / len(rows), 2) if rows else None,
                        "model_version": current_app.config["ML_MODEL_VERSION"], "dataset": "synthetic CSV"})
    finally:
        connection.close()

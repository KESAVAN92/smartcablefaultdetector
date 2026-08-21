from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .feature_engineering import build_live_row, row_to_features
from .model_manager import ModelManager


class PredictionService:
    def __init__(self, app):
        self.app = app
        self.manager = ModelManager(app.config["ML_DATASET_PATH"], version=app.config["ML_MODEL_VERSION"])

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.app.config["DATABASE_PATH"])
        connection.row_factory = sqlite3.Row
        ensure_prediction_schema(connection)
        return connection

    def predict(self, reading: dict[str, Any], *, fault_event_id: int | None = None) -> dict[str, Any]:
        result = self.manager.predict(row_to_features(build_live_row(reading)))
        top = result["top_predictions"]
        confidence = top[0]["confidence"] if top else 0.0
        predicted_fault = top[0]["fault_type"] if top else "UNKNOWN"
        if result["is_anomaly"] and confidence < self.app.config["ML_UNKNOWN_CONFIDENCE_THRESHOLD"]:
            predicted_fault = "UNKNOWN"
        rul = result["rul"]
        health = self.health_score(reading, result, confidence)
        alert_level = self.alert_level(reading, result, health)
        timestamp = datetime.now(timezone.utc).isoformat()
        connection = self._connection()
        try:
            cursor = connection.execute(
                """INSERT INTO ml_predictions
                (reading_id, fault_event_id, edge_id, predicted_fault_type, confidence, anomaly_score,
                 is_anomaly, health_score, remaining_life_days, failure_probability_30d,
                 failure_probability_90d, failure_probability_180d, model_version, prediction_timestamp,
                 explanation, model_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (reading.get("id"), fault_event_id, reading.get("edge_id"), predicted_fault, confidence,
                 result["anomaly_score"], int(result["is_anomaly"]), health, rul.get("remaining_life_days"),
                 rul.get("failure_probability_30d"), rul.get("failure_probability_90d"),
                 rul.get("failure_probability_180d"), result["model_version"], timestamp,
                 ", ".join(result["explanation"]), result["model_source"]),
            )
            connection.commit()
            prediction_id = cursor.lastrowid
        finally:
            connection.close()
        return {"prediction_id": prediction_id, "fault_type": predicted_fault, "confidence": confidence,
                **result, "health_score": health, "remaining_life_days": rul.get("remaining_life_days"),
                "failure_probability_30d": rul.get("failure_probability_30d"),
                "failure_probability_90d": rul.get("failure_probability_90d"),
                "failure_probability_180d": rul.get("failure_probability_180d"), "alert_level": alert_level}

    def health_score(self, reading: dict[str, Any], result: dict[str, Any], confidence: float) -> float:
        history_penalty = min(30.0, float(reading.get("fault_count_30d", 0)) * 2)
        overload_penalty = min(20.0, float(reading.get("overload_count_30d", 0)) * 2)
        score = 100 - history_penalty - overload_penalty - result["anomaly_score"] * 20 - confidence * 10
        return round(max(0.0, min(100.0, score)), 2)

    def alert_level(self, reading, result, health):
        if reading.get("is_overload"):
            return "CRITICAL"
        if result["is_anomaly"] or health < 50:
            return "WARNING"
        return "INFO"


def ensure_prediction_schema(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS ml_predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, reading_id INTEGER, fault_event_id INTEGER,
        edge_id TEXT, predicted_fault_type TEXT NOT NULL, confidence REAL NOT NULL,
        anomaly_score REAL NOT NULL, is_anomaly INTEGER NOT NULL, health_score REAL NOT NULL,
        remaining_life_days REAL, failure_probability_30d REAL, failure_probability_90d REAL,
        failure_probability_180d REAL, model_version TEXT NOT NULL, prediction_timestamp TEXT NOT NULL,
        explanation TEXT, model_source TEXT
    )""")
    connection.commit()

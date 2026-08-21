from __future__ import annotations

from pathlib import Path

from ml.feature_engineering import FEATURE_COLUMNS, chronological_split, load_training_rows, row_to_features
from ml.model_manager import ModelManager
from ml.prediction_service import PredictionService


DATASET = Path(__file__).resolve().parents[2] / "underground_cable_ml_dataset_30000 (8).csv"


def test_dataset_features_are_labeled_and_temporally_split():
    rows = load_training_rows(DATASET)
    train, validation, test = chronological_split(rows)
    assert len(rows) == 30000
    assert len(row_to_features(rows[0])) == len(FEATURE_COLUMNS)
    assert rows[0]["timestamp"] < rows[-1]["timestamp"]
    assert len(train) == 21000
    assert len(validation) == 4500
    assert len(test) == 4500


def test_model_returns_top_three_and_real_metrics():
    rows = load_training_rows(DATASET)
    manager = ModelManager(str(DATASET))
    result = manager.predict(row_to_features(rows[0]))
    assert len(result["top_predictions"]) == 3
    assert all(0 <= item["confidence"] <= 1 for item in result["top_predictions"])
    assert manager.metrics["class_count"] == 8
    assert manager.metrics["split"] == "chronological 70/15/15"


def test_health_score_and_alert_are_bounded():
    class App:
        config = {"ML_DATASET_PATH": str(DATASET), "ML_MODEL_VERSION": "test", "ML_UNKNOWN_CONFIDENCE_THRESHOLD": 0.5}

    service = PredictionService(App())
    result = {"anomaly_score": 0.9, "is_anomaly": True}
    assert service.health_score({"fault_count_30d": 8, "overload_count_30d": 4}, result, 0.8) == 50.0
    assert service.alert_level({"is_overload": False}, result, 40) == "WARNING"

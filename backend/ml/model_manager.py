from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestRegressor, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

from .feature_engineering import FEATURE_COLUMNS, chronological_split, load_training_rows, row_to_features

try:
    from xgboost import XGBClassifier
except ImportError:  # Optional in local/dev environments; requirements installs it for production.
    XGBClassifier = None


class ModelManager:
    def __init__(self, dataset_path: str, *, version: str = "ml-demo-2026.08"):
        self.dataset_path = dataset_path
        self.version = version
        self._lock = Lock()
        self.classifier: Any = None
        self.anomaly_detector: IsolationForest | None = None
        self.rul_models: dict[str, RandomForestRegressor] = {}
        self.classes: list[str] = []
        self.metrics: dict[str, Any] = {}
        self.source = "unavailable"

    def ensure_ready(self) -> None:
        if self.classifier is not None:
            return
        with self._lock:
            if self.classifier is not None:
                return
            rows = load_training_rows(self.dataset_path)
            if len(rows) < 30:
                raise RuntimeError("Insufficient labeled rows for ML training.")
            train_rows, validation_rows, test_rows = chronological_split(rows)
            self.classes = sorted({row["fault_type"] for row in rows})
            x_train = np.asarray([row_to_features(row) for row in train_rows])
            y_train = np.asarray([row["fault_type"] for row in train_rows])
            x_test = np.asarray([row_to_features(row) for row in test_rows])
            y_test = np.asarray([row["fault_type"] for row in test_rows])

            if XGBClassifier is not None:
                labels = {name: index for index, name in enumerate(self.classes)}
                self.classifier = XGBClassifier(
                    n_estimators=90, max_depth=5, learning_rate=0.08,
                    objective="multi:softprob", eval_metric="mlogloss",
                    num_class=len(self.classes), tree_method="hist", n_jobs=2,
                    random_state=42,
                )
                self.classifier.fit(x_train, np.asarray([labels[value] for value in y_train]))
                self.source = "XGBoost"
            else:
                self.classifier = RandomForestClassifier(
                    n_estimators=120, class_weight="balanced", random_state=42, n_jobs=2
                )
                self.classifier.fit(x_train, y_train)
                self.source = "RandomForest fallback (install xgboost for primary model)"

            anomaly_rows = np.asarray([row_to_features(row) for row in train_rows])
            self.anomaly_detector = IsolationForest(contamination="auto", random_state=42, n_estimators=100)
            self.anomaly_detector.fit(anomaly_rows)

            for target in ("remaining_life_days", "failure_probability_30d", "failure_probability_90d", "failure_probability_180d"):
                targets = np.asarray([float(row[target]) for row in train_rows])
                model = RandomForestRegressor(n_estimators=80, random_state=42, n_jobs=2)
                model.fit(x_train, targets)
                self.rul_models[target] = model

            predictions = self.classifier.predict(x_test)
            if self.source == "XGBoost":
                predictions = np.asarray([self.classes[int(value)] for value in predictions])
            comparison = {}
            logistic = LogisticRegression(max_iter=1000, class_weight="balanced")
            logistic.fit(x_train, y_train)
            comparison["LogisticRegression"] = round(float(f1_score(y_test, logistic.predict(x_test), average="macro")), 4)
            comparison_rf = RandomForestClassifier(
                n_estimators=120, class_weight="balanced", random_state=42, n_jobs=2
            )
            comparison_rf.fit(x_train, y_train)
            comparison["RandomForest"] = round(float(f1_score(y_test, comparison_rf.predict(x_test), average="macro")), 4)
            comparison["XGBoost"] = round(float(f1_score(y_test, predictions, average="macro")), 4) if XGBClassifier is not None else None
            if comparison["RandomForest"] > (comparison["XGBoost"] or 0):
                self.classifier = comparison_rf
                self.source = "RandomForest (selected by chronological macro-F1)"
                selected_predictions = comparison_rf.predict(x_test)
            else:
                selected_predictions = predictions
            self.metrics = {
                "training_samples": len(train_rows), "validation_samples": len(validation_rows),
                "test_samples": len(test_rows), "class_count": len(self.classes),
                "macro_f1": round(float(f1_score(y_test, selected_predictions, average="macro")), 4),
                "split": "chronological 70/15/15", "dataset_source": "synthetic CSV",
                "selected_model": self.source,
                "model_comparison_macro_f1": comparison,
            }

    def predict(self, features: list[float]) -> dict[str, Any]:
        self.ensure_ready()
        vector = np.asarray([features])
        probabilities = self.classifier.predict_proba(vector)[0]
        model_classes = list(self.classifier.classes_)
        if self.source == "XGBoost":
            model_classes = [self.classes[int(value)] for value in model_classes]
        ranked = sorted(zip(model_classes, probabilities), key=lambda item: item[1], reverse=True)
        anomaly_raw = float(self.anomaly_detector.decision_function(vector)[0])
        anomaly_score = max(0.0, min(1.0, 0.5 - anomaly_raw))
        top_features = sorted(
            zip(FEATURE_COLUMNS, getattr(self.classifier, "feature_importances_", np.zeros(len(FEATURE_COLUMNS)))),
            key=lambda item: item[1], reverse=True,
        )[:5]
        return {
            "top_predictions": [{"fault_type": str(label), "confidence": round(float(score), 4)} for label, score in ranked[:3]],
            "anomaly_score": round(anomaly_score, 4), "is_anomaly": anomaly_score >= 0.80,
            "explanation": [name for name, _ in top_features],
            "rul": {name: round(max(0.0, float(model.predict(vector)[0])), 2) for name, model in self.rul_models.items()},
            "model_version": self.version, "model_source": self.source,
        }

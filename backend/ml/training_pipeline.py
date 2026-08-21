"""Reproducible chronological training entry point.

Run from the repository root with: python -m ml.training_pipeline (PYTHONPATH=backend).
The CSV is synthetic project simulation data, so metrics describe this dataset only.
"""

from __future__ import annotations

import json
import os

from .model_manager import ModelManager


def main() -> None:
    dataset = os.environ.get("ML_DATASET_PATH", "underground_cable_ml_dataset_30000 (8).csv")
    manager = ModelManager(dataset)
    manager.ensure_ready()
    print(json.dumps(manager.metrics, indent=2))
    print("The selected model is chosen by chronological macro-F1; XGBoost remains the primary candidate when it wins.")


if __name__ == "__main__":
    main()

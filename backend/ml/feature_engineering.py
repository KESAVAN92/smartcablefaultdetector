from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

FAULT_CLASSES = [
    "NORMAL",
    "SHORT_CIRCUIT",
    "OPEN_CIRCUIT",
    "INSULATION_FAILURE",
    "EARTH_FAULT",
    "HIGH_RESISTANCE_FAULT",
    "OVERLOAD",
    "INTERMITTENT_FAULT",
]

FEATURE_COLUMNS = [
    "adc_value", "current_amps", "voltage_x", "resistance_x_ohm", "distance_m",
    "cable_age_years", "cable_length_m", "resistance_per_m_ohm", "is_overload",
    "fault_count_7d", "fault_count_30d", "fault_count_90d", "overload_count_7d",
    "overload_count_30d", "days_since_last_fault", "days_since_last_overload",
    "resistance_mean_7d", "resistance_mean_30d", "resistance_std_7d",
    "resistance_slope_7d", "current_mean_7d", "current_slope_7d",
    "voltage_mean_7d", "voltage_slope_7d",
]


def _number(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def row_to_features(row: dict[str, Any]) -> list[float]:
    values = [_number(row.get(column)) for column in FEATURE_COLUMNS]
    values[4] = _number(row.get("distance_m"), 0.0)
    values[8] = 1.0 if str(row.get("is_overload", "")).lower() in {"1", "true", "yes"} else 0.0
    return values


def load_training_rows(dataset_path: str | Path) -> list[dict[str, Any]]:
    with Path(dataset_path).open("r", encoding="utf-8-sig", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row.get("fault_type") in FAULT_CLASSES]
    rows.sort(key=lambda row: row.get("timestamp", ""))
    return rows


def build_live_row(reading: dict[str, Any]) -> dict[str, Any]:
    """Map the deterministic sensor contract into the shared feature schema."""
    return {
        **reading,
        "resistance_x_ohm": reading.get("resistance_x", reading.get("resistance_x_ohm")),
        "distance_m": reading.get("distance_m") or 0.0,
        "is_overload": reading.get("is_overload", False),
        "resistance_mean_7d": reading.get("resistance_x", 0.0),
        "resistance_mean_30d": reading.get("resistance_x", 0.0),
        "current_mean_7d": reading.get("current_amps", 0.0),
        "voltage_mean_7d": reading.get("voltage_x", 0.0),
    }


def chronological_split(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    first = int(len(rows) * 0.70)
    second = int(len(rows) * 0.85)
    return rows[:first], rows[first:second], rows[second:]

"""
Module 1 Adapter — lives inside modules/module3/adapters/ (Module 3's territory).



This file implements:
  • The exact hardware formula pipeline from project report Section 9.2
  • Inverse computation for fault injection
  • Overload detection (report Section 13 — overload ⟹ no distance)
  • Background thread emitting idle + injected readings via SocketIO
  • Does NOT write to any database table — that is Module 1's job.
    fault_events.reading_id stores the UUID we generate; when M1 persists
    the same reading with the same UUID, the reference becomes valid.

Validated fixture (Section 9.2):
    ADC=200, Rc=0.01 → Vx=0.9766V, Rx=9.375Ω, Distance=468.75m  (within 0.1 tol)
"""

from __future__ import annotations

import random
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

# ── Named constants — Section 9.2 ─────────────────────────────────────────────
ACS712_CURRENT_CONSTANT: float = 1.25 / 12      # I = 0.104167 A
ADC_VREF: float = 5.0                            # reference voltage (V)
ADC_RESOLUTION: int = 1024                       # 10-bit ADC
DEFAULT_RC_OHMS_PER_M: float = 0.01             # Ω/m default cable resistance
OVERLOAD_THRESHOLD_AMPS: float = 5.0            # current above this → is_overload=True
IDLE_ADC_MAX: int = 30                           # idle readings stay under this ADC

# ── Module-level singletons ────────────────────────────────────────────────────
_socketio = None
_mapping_process_fn = None          # set by init — avoids circular import
_pending_fault: Optional[dict] = None
_lock = threading.Lock()


# ── Formula pipeline (Section 9.2) ────────────────────────────────────────────

def compute_fault_reading(adc_value: int, rc_ohms_per_m: float = DEFAULT_RC_OHMS_PER_M) -> dict:
    """
    Run the hardware formula pipeline on a raw ADC reading.

    Vx  = (ADC × 5) / 1024
    Rx  = Vx / I          where I = ACS712_CURRENT_CONSTANT
    Dist = (Rx / Rc) / 2

    Returns a dict matching the fault_readings table schema (no id/recorded_at).
    """
    if not (0 <= adc_value <= 1023):
        raise ValueError(f"ADC value must be in [0, 1023], got {adc_value}")
    if rc_ohms_per_m <= 0:
        raise ValueError(f"Rc must be > 0, got {rc_ohms_per_m}")

    I: float = ACS712_CURRENT_CONSTANT
    vx: float = (adc_value * ADC_VREF) / ADC_RESOLUTION
    rx: float = vx / I

    # Section 13: overload entries have NO distance value
    is_overload: bool = I > OVERLOAD_THRESHOLD_AMPS
    distance_m: Optional[float] = None if is_overload else (rx / rc_ohms_per_m) / 2

    return {
        "adc_value": adc_value,
        "current_amps": round(I, 6),
        "voltage_x": round(vx, 4),
        "resistance_x": round(rx, 4),
        "distance_m": round(distance_m, 2) if distance_m is not None else None,
        "is_overload": is_overload,
    }


def inverse_compute_adc(
    *,
    target_distance_m: Optional[float] = None,
    target_resistance_ohms: Optional[float] = None,
    rc_ohms_per_m: float = DEFAULT_RC_OHMS_PER_M,
) -> int:
    """
    Invert the pipeline so injected faults are indistinguishable from real ones.

    Distance = (Rx/Rc)/2  →  Rx = Distance × Rc × 2
    Rx = Vx/I             →  Vx = Rx × I
    Vx = (ADC×5)/1024     →  ADC = (Vx×1024)/5
    """
    if target_distance_m is None and target_resistance_ohms is None:
        raise ValueError("Provide target_distance_m or target_resistance_ohms")
    if target_distance_m is not None and target_distance_m < 0:
        raise ValueError("target_distance_m must be >= 0")
    if target_resistance_ohms is not None and target_resistance_ohms < 0:
        raise ValueError("target_resistance_ohms must be >= 0")

    if target_resistance_ohms is None:
        target_resistance_ohms = target_distance_m * rc_ohms_per_m * 2

    vx = target_resistance_ohms * ACS712_CURRENT_CONSTANT
    adc = round((vx * ADC_RESOLUTION) / ADC_VREF)
    return max(0, min(1023, adc))


def build_full_reading(
    adc_value: int,
    source_node_id: str,
    rc_ohms_per_m: float = DEFAULT_RC_OHMS_PER_M,
    is_injected: bool = False,
) -> dict:
    """Combine compute_fault_reading with metadata fields."""
    computed = compute_fault_reading(adc_value, rc_ohms_per_m)
    return {
        "id": str(uuid.uuid4()),
        "source_node_id": source_node_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "_is_injected": is_injected,   # internal flag — not stored in DB
        **computed,
    }


# ── Background emission loop ───────────────────────────────────────────────────

def _clear_pending() -> Optional[dict]:
    global _pending_fault
    with _lock:
        fault = _pending_fault
        _pending_fault = None
    return fault


def _background_loop():
    default_source = "node-main-panel"

    while True:
        time.sleep(2)
        try:
            pending = _clear_pending()
            if pending:
                reading = pending
            else:
                # Idle noise — small ADC (distance stays well below fault threshold)
                adc = random.randint(0, IDLE_ADC_MAX)
                reading = build_full_reading(adc, default_source, DEFAULT_RC_OHMS_PER_M, False)

            # Broadcast to WebSocket clients on /readings namespace
            if _socketio:
                _socketio.emit("new_reading", reading, namespace="/readings")

            # Hand off to mapping service (only injected faults trigger fault_events)
            if _mapping_process_fn:
                _mapping_process_fn(reading)

        except Exception as exc:
            print(f"[m1_adapter] background loop error: {exc}")


def schedule_fault(reading_dict: dict):
    """Called by the inject-fault endpoint — queues reading for next emission tick."""
    global _pending_fault
    with _lock:
        _pending_fault = reading_dict


def init_module1_adapter(socketio, mapping_process_fn=None, *, start_background=True):
    """
    Called from modules/module3/__init__.py after SocketIO is ready.
    mapping_process_fn is injected to avoid circular imports.
    """
    global _socketio, _mapping_process_fn
    _socketio = socketio
    if mapping_process_fn:
        _mapping_process_fn = mapping_process_fn
    if start_background:
        t = threading.Thread(target=_background_loop, daemon=True, name="m1-adapter-loop")
        t.start()
        print("[m1_adapter] background emission loop started")

"""
Module 3 Mapping Service — the project's core innovation.

Pipeline:
  fault_reading (from M1 adapter)
      ↓
  graph_nearest() (via M2 adapter)
      ↓
  fault_events row written to DB
      ↓
  broadcast on SocketIO /fault-events namespace
      ↓
  frontend Leaflet map renders marker

Only readings flagged _is_injected=True create fault_events (idle noise is ignored).
Overload readings are always skipped.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from database import SessionLocal
from models.fault_events import FaultEvent
from modules.module3.adapters.module2_adapter import graph_nearest

# ── Config ────────────────────────────────────────────────────────────────────
# Minimum distance to be treated as a real fault (not idle noise)
FAULT_DISTANCE_THRESHOLD_M: float = 50.0

_socketio = None


def init_mapping_service(socketio):
    """Called from modules/module3/__init__.py after SocketIO is ready."""
    global _socketio
    _socketio = socketio
    print("[mapping_service] initialised")


def process_reading(reading: dict) -> dict | None:
    """
    Entry point called by the M1 adapter for every reading.
    Returns the created FaultEvent dict if one was created, else None.

    Rules (matching report Sections 9.2 and 13):
      - Skip overloads (no distance to map)
      - Skip idle noise (distance_m below threshold OR _is_injected=False)
      - For real faults: resolve graph position → persist → broadcast
    """
    # Guard: overloads never have a location
    if reading.get("is_overload"):
        return None

    distance_m = reading.get("distance_m")
    if distance_m is None:
        return None

    # Only process readings explicitly injected as faults
    if not reading.get("_is_injected", False):
        return None

    source_node_id = reading.get("source_node_id", "node-main-panel")

    # ── Step 1: Resolve graph position ────────────────────────────────────────
    try:
        graph_pos = graph_nearest(source_node_id=source_node_id, distance_m=distance_m)
    except ValueError as exc:
        print(f"[mapping_service] graph_nearest error: {exc}")
        return None

    # ── Step 2: Persist fault_event ───────────────────────────────────────────
    db = SessionLocal()
    try:
        event = FaultEvent(
            id=str(uuid.uuid4()),
            reading_id=reading["id"],
            nearest_node_id=graph_pos["nearest_node_id"],
            edge_id=graph_pos.get("edge_id"),
            distance_along_edge_m=graph_pos.get("distance_along_edge_m"),
            status="open",
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        event_dict = event.to_dict()
    finally:
        db.close()

    # ── Step 3: Broadcast to WebSocket clients ────────────────────────────────
    payload = {
        **event_dict,
        "reading": {k: v for k, v in reading.items() if not k.startswith("_")},
        "graph_position": graph_pos,
    }
    if _socketio:
        _socketio.emit("new_fault_event", payload, namespace="/fault-events")

    print(
        f"[mapping_service] fault_event created: {event.id} "
        f"node={graph_pos['nearest_node_id']} "
        f"beyond_graph={graph_pos.get('beyond_graph', False)}"
    )
    return payload

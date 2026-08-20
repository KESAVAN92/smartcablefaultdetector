"""
Module 3 REST routes + WebSocket namespace handlers.

Endpoints owned by Module 3:
  GET  /api/module3/                            — status
  GET  /api/module3/fault-events                — list with filters
  POST /api/module3/fault-events/<id>/acknowledge
  POST /api/module3/fault-events/<id>/resolve
  GET  /api/module3/graph                       — graph data for frontend map
  POST /api/module3/simulate/inject-fault       — test injection endpoint
  WS   /readings                                — raw reading stream (M1 proxy)
  WS   /fault-events                            — fault event stream (M3)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import os

from flask import Blueprint, jsonify, request, send_from_directory, current_app
from flask_socketio import Namespace

from database import SessionLocal
from models.fault_events import FaultEvent
from modules.module3.adapters.module1_adapter import (
    ACS712_CURRENT_CONSTANT,
    DEFAULT_RC_OHMS_PER_M,
    build_full_reading,
    inverse_compute_adc,
    schedule_fault,
)
from modules.module3.adapters.module2_adapter import get_full_graph
from modules.module3.mapping_service import process_reading

module3_bp = Blueprint("module3", __name__)


# ── Utility ───────────────────────────────────────────────────────────────────

def _error(msg: str, code: int = 422):
    return jsonify({"error": msg}), code


# ── Status ────────────────────────────────────────────────────────────────────

@module3_bp.get("/")
def module3_status():
    return jsonify({
        "module": "module3",
        "purpose": "Fault-to-Graph Mapping & Live Digital Map",
        "status": "active",
        "endpoints": [
            "GET  /api/module3/fault-events",
            "POST /api/module3/fault-events/<id>/acknowledge",
            "POST /api/module3/fault-events/<id>/resolve",
            "GET  /api/module3/graph",
            "POST /api/module3/simulate/inject-fault",
            "WS   /readings  (namespace, event: new_reading)",
            "WS   /fault-events  (namespace, event: new_fault_event)",
        ],
    })


# ── Graph data (proxies M2 adapter) ──────────────────────────────────────────

@module3_bp.get("/graph")
def get_graph():
    """Return full node/edge list for the Leaflet map frontend."""
    return jsonify(get_full_graph())


@module3_bp.get("/layout-image")
def get_layout_image():
    """Serve the NEC campus cable layout chart image for the Leaflet map."""
    static_dir = os.path.join(current_app.root_path, "static")
    return send_from_directory(static_dir, "nec_layout.jpg", mimetype="image/jpeg")


# ── Fault Events REST API ─────────────────────────────────────────────────────

@module3_bp.get("/fault-events")
def list_fault_events():
    """
    GET /api/module3/fault-events
    Query params:
      status       — open | acknowledged | resolved
      node_id      — nearest_node_id filter
      from_date    — ISO-8601 start (created_at >=)
      to_date      — ISO-8601 end   (created_at <=)
      limit        — max rows (default 100)
    """
    db = SessionLocal()
    try:
        q = db.query(FaultEvent)

        status = request.args.get("status")
        if status:
            if status not in ("open", "acknowledged", "resolved"):
                return _error("status must be open|acknowledged|resolved")
            q = q.filter(FaultEvent.status == status)

        node_id = request.args.get("node_id")
        if node_id:
            q = q.filter(FaultEvent.nearest_node_id == node_id)

        from_date = request.args.get("from_date")
        if from_date:
            try:
                dt = datetime.fromisoformat(from_date)
                q = q.filter(FaultEvent.created_at >= dt)
            except ValueError:
                return _error("from_date must be ISO-8601")

        to_date = request.args.get("to_date")
        if to_date:
            try:
                dt = datetime.fromisoformat(to_date)
                q = q.filter(FaultEvent.created_at <= dt)
            except ValueError:
                return _error("to_date must be ISO-8601")

        try:
            limit = int(request.args.get("limit", 100))
            if limit < 1 or limit > 1000:
                raise ValueError
        except ValueError:
            return _error("limit must be an integer between 1 and 1000")

        events = q.order_by(FaultEvent.created_at.desc()).limit(limit).all()
        return jsonify([e.to_dict() for e in events])
    finally:
        db.close()


@module3_bp.post("/fault-events/<event_id>/acknowledge")
def acknowledge_event(event_id: str):
    db = SessionLocal()
    try:
        event = db.get(FaultEvent, event_id)
        if not event:
            return _error("fault_event not found", 404)
        if event.status != "open":
            return _error(f"event is already {event.status}")
        # acknowledged_by placeholder — auth is Module 4's job
        body = request.get_json(silent=True) or {}
        event.status = "acknowledged"
        event.acknowledged_by = body.get("acknowledged_by", "anonymous")
        db.commit()
        return jsonify(event.to_dict())
    finally:
        db.close()


@module3_bp.post("/fault-events/<event_id>/resolve")
def resolve_event(event_id: str):
    db = SessionLocal()
    try:
        event = db.get(FaultEvent, event_id)
        if not event:
            return _error("fault_event not found", 404)
        if event.status == "resolved":
            return _error("event is already resolved")
        event.status = "resolved"
        event.resolved_at = datetime.now(timezone.utc)
        db.commit()
        return jsonify(event.to_dict())
    finally:
        db.close()


# ── Fault Injection (Module 3's test endpoint) ────────────────────────────────

@module3_bp.post("/simulate/inject-fault")
def inject_fault():
    """
    POST /api/module3/simulate/inject-fault
    Body (JSON):
      source_node_id         string  (required)
      target_distance_m      float   (one of these two required)
      target_resistance_ohms float
      rc_ohms_per_m          float   (default 0.01)
      overload               bool    (default false)

    Computes the ADC value that would produce this fault via inverse pipeline,
    then runs it through the same engine — so injected faults are
    indistinguishable from real sensor readings.

    TODO-integrate: when M1 is live, this can also call their endpoint at
    POST /api/module1/simulate/inject-fault for full end-to-end testing.
    """
    body = request.get_json(silent=True)
    if not body:
        return _error("JSON body required")

    source_node_id = body.get("source_node_id")
    if not source_node_id:
        return _error("source_node_id is required")

    overload: bool = bool(body.get("overload", False))
    rc: float = float(body.get("rc_ohms_per_m", DEFAULT_RC_OHMS_PER_M))
    if rc <= 0:
        return _error("rc_ohms_per_m must be > 0")

    if overload:
        # Overload reading — maximum ADC, no distance
        reading = {
            "id": str(uuid.uuid4()),
            "source_node_id": source_node_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "adc_value": 1023,
            "current_amps": round(ACS712_CURRENT_CONSTANT, 6),
            "voltage_x": None,
            "resistance_x": None,
            "distance_m": None,
            "is_overload": True,
            "_is_injected": True,
        }
    else:
        t_dist = body.get("target_distance_m")
        t_res = body.get("target_resistance_ohms")
        if t_dist is None and t_res is None:
            return _error("provide target_distance_m or target_resistance_ohms")
        if t_dist is not None and float(t_dist) < 0:
            return _error("target_distance_m must be >= 0")
        if t_res is not None and float(t_res) < 0:
            return _error("target_resistance_ohms must be >= 0")

        try:
            adc = inverse_compute_adc(
                target_distance_m=float(t_dist) if t_dist is not None else None,
                target_resistance_ohms=float(t_res) if t_res is not None else None,
                rc_ohms_per_m=rc,
            )
        except ValueError as exc:
            return _error(str(exc))

        reading = build_full_reading(adc, source_node_id, rc, is_injected=True)

    # Queue for the background emission loop AND process immediately
    schedule_fault(reading)
    fault_event = process_reading(reading)

    return jsonify({
        "reading": {k: v for k, v in reading.items() if not k.startswith("_")},
        "fault_event": fault_event,
    }), 201


# ── WebSocket Namespace Handlers ──────────────────────────────────────────────

class ReadingsNamespace(Namespace):
    """Clients subscribe here to receive raw sensor readings from Module 1."""

    def on_connect(self):
        print("[WS /readings] client connected")

    def on_disconnect(self, *args):
        print("[WS /readings] client disconnected")


class FaultEventsNamespace(Namespace):
    """Clients subscribe here to receive live fault events from Module 3."""

    def on_connect(self):
        print("[WS /fault-events] client connected")

    def on_disconnect(self, *args):
        print("[WS /fault-events] client disconnected")

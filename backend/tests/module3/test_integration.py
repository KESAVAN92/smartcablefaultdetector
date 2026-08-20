"""
Integration tests — end-to-end: POST inject-fault → fault_event in DB → WS broadcast.
"""

import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
import json


class TestInjectFaultEndpoint:
    """POST /api/module3/simulate/inject-fault integration tests."""

    def test_inject_fault_returns_201(self, test_client):
        resp = test_client.post(
            "/api/module3/simulate/inject-fault",
            json={
                "source_node_id": "node-main-panel",
                "target_distance_m": 468.75,
                "rc_ohms_per_m": 0.01,
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "reading" in data
        assert "fault_event" in data

    def test_inject_creates_fault_event_in_db(self, test_client):
        resp = test_client.post(
            "/api/module3/simulate/inject-fault",
            json={
                "source_node_id": "node-main-panel",
                "target_distance_m": 300.0,
                "rc_ohms_per_m": 0.01,
            },
        )
        assert resp.status_code == 201
        event_id = resp.get_json()["fault_event"]["id"]

        # Verify row in DB via GET /fault-events
        list_resp = test_client.get("/api/module3/fault-events")
        assert list_resp.status_code == 200
        events = list_resp.get_json()
        ids = [e["id"] for e in events]
        assert event_id in ids

    def test_inject_reading_values_match_formula(self, test_client):
        """Verify the Section 9.2 fixture through the HTTP API."""
        resp = test_client.post(
            "/api/module3/simulate/inject-fault",
            json={
                "source_node_id": "node-main-panel",
                "target_distance_m": 468.75,
                "rc_ohms_per_m": 0.01,
            },
        )
        reading = resp.get_json()["reading"]
        assert abs(reading["voltage_x"] - 0.9766) < 0.1
        assert abs(reading["resistance_x"] - 9.375) < 0.1
        assert abs(reading["distance_m"] - 468.75) < 1.0   # ±1m after int ADC rounding

    def test_inject_overload_no_fault_event(self, test_client):
        """Overload injection must not create a fault_event."""
        resp = test_client.post(
            "/api/module3/simulate/inject-fault",
            json={
                "source_node_id": "node-main-panel",
                "overload": True,
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["reading"]["is_overload"] is True
        assert data["fault_event"] is None

    def test_inject_missing_source_node_422(self, test_client):
        resp = test_client.post(
            "/api/module3/simulate/inject-fault",
            json={"target_distance_m": 100},
        )
        assert resp.status_code == 422

    def test_inject_missing_target_422(self, test_client):
        resp = test_client.post(
            "/api/module3/simulate/inject-fault",
            json={"source_node_id": "node-main-panel"},
        )
        assert resp.status_code == 422

    def test_inject_negative_distance_422(self, test_client):
        resp = test_client.post(
            "/api/module3/simulate/inject-fault",
            json={"source_node_id": "node-main-panel", "target_distance_m": -10},
        )
        assert resp.status_code == 422

    def test_inject_rc_zero_422(self, test_client):
        resp = test_client.post(
            "/api/module3/simulate/inject-fault",
            json={
                "source_node_id": "node-main-panel",
                "target_distance_m": 100,
                "rc_ohms_per_m": 0,
            },
        )
        assert resp.status_code == 422


class TestFaultEventsAPI:
    """REST CRUD for fault_events."""

    def _inject(self, test_client, distance_m=300.0):
        return test_client.post(
            "/api/module3/simulate/inject-fault",
            json={
                "source_node_id": "node-main-panel",
                "target_distance_m": distance_m,
                "rc_ohms_per_m": 0.01,
            },
        )

    def test_list_empty(self, test_client):
        resp = test_client.get("/api/module3/fault-events")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_list_after_inject(self, test_client):
        self._inject(test_client)
        resp = test_client.get("/api/module3/fault-events")
        assert len(resp.get_json()) == 1

    def test_filter_by_status(self, test_client):
        self._inject(test_client)
        resp = test_client.get("/api/module3/fault-events?status=open")
        assert all(e["status"] == "open" for e in resp.get_json())

    def test_acknowledge_event(self, test_client):
        event_id = self._inject(test_client).get_json()["fault_event"]["id"]
        resp = test_client.post(
            f"/api/module3/fault-events/{event_id}/acknowledge",
            json={"acknowledged_by": "engineer-1"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "acknowledged"
        assert data["acknowledged_by"] == "engineer-1"

    def test_resolve_event(self, test_client):
        event_id = self._inject(test_client).get_json()["fault_event"]["id"]
        test_client.post(f"/api/module3/fault-events/{event_id}/acknowledge")
        resp = test_client.post(f"/api/module3/fault-events/{event_id}/resolve")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "resolved"
        assert data["resolved_at"] is not None

    def test_acknowledge_nonexistent_404(self, test_client):
        resp = test_client.post("/api/module3/fault-events/no-such-id/acknowledge")
        assert resp.status_code == 404

    def test_invalid_status_filter_422(self, test_client):
        resp = test_client.get("/api/module3/fault-events?status=invalid")
        assert resp.status_code == 422


class TestWebSocketBroadcast:
    """Integration: inject fault → assert broadcast on WS /fault-events within timeout."""

    def test_fault_event_broadcast_on_ws(self, flask_app, test_client):
        import app as app_module
        sio_client = app_module.socketio.test_client(
            flask_app, namespace="/fault-events"
        )
        assert sio_client.is_connected(namespace="/fault-events")

        # Inject fault
        resp = test_client.post(
            "/api/module3/simulate/inject-fault",
            json={
                "source_node_id": "node-main-panel",
                "target_distance_m": 300.0,
                "rc_ohms_per_m": 0.01,
            },
        )
        assert resp.status_code == 201
        event_id = resp.get_json()["fault_event"]["id"]

        # Collect emitted events (synchronous in test mode)
        received = sio_client.get_received(namespace="/fault-events")
        event_names = [e["name"] for e in received]
        assert "new_fault_event" in event_names, (
            f"Expected 'new_fault_event' in {event_names}"
        )

        payload = next(e["args"][0] for e in received if e["name"] == "new_fault_event")
        assert payload["id"] == event_id
        assert payload["status"] == "open"
        assert "graph_position" in payload
        sio_client.disconnect(namespace="/fault-events")

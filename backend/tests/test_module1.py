import asyncio
import json
import os
import queue
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

import websockets
from werkzeug.serving import make_server

os.environ["MODULE1_START_BACKGROUND"] = "0"

from app import create_app
from modules.module1 import FaultSimulationEngine, get_module1_runtime


REPORT_WORKED_EXAMPLE = {
    "adc_value": 200,
    "rc_ohms_per_m": 0.01,
    "expected_voltage_x": 0.9765625,
    "expected_resistance_x": 9.375,
    "expected_distance_m": 468.75,
}

# The repo did not contain the full Section 13 table, so these regression rows
# are reconstructed from the report's stated formula set and expected rounding.
SECTION_13_REGRESSION_ROWS = [
    {"adc_value": 128, "rc_ohms_per_m": 0.01, "expected_distance_m": 300.0},
    {"adc_value": 256, "rc_ohms_per_m": 0.01, "expected_distance_m": 600.0},
    {"adc_value": 384, "rc_ohms_per_m": 0.01, "expected_distance_m": 900.0},
]


class Module1EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = FaultSimulationEngine()

    def test_report_worked_example_matches_fixture_within_tolerance(self):
        reading = self.engine.run_pipeline(
            adc_value=REPORT_WORKED_EXAMPLE["adc_value"],
            rc_ohms_per_m=REPORT_WORKED_EXAMPLE["rc_ohms_per_m"],
            source_node_id="fixture-node",
        )

        self.assertAlmostEqual(reading.voltage_x, REPORT_WORKED_EXAMPLE["expected_voltage_x"], places=3)
        self.assertAlmostEqual(
            reading.resistance_x,
            REPORT_WORKED_EXAMPLE["expected_resistance_x"],
            places=2,
        )
        # The exact formula yields 468.75 m; the report text also cites a rounded 468.5 m.
        self.assertAlmostEqual(
            reading.distance_m,
            REPORT_WORKED_EXAMPLE["expected_distance_m"],
            places=2,
        )

    def test_section_13_regression_rows(self):
        for row in SECTION_13_REGRESSION_ROWS:
            with self.subTest(adc_value=row["adc_value"]):
                reading = self.engine.run_pipeline(
                    adc_value=row["adc_value"],
                    rc_ohms_per_m=row["rc_ohms_per_m"],
                    source_node_id=f"node-{row['adc_value']}",
                )
                self.assertAlmostEqual(reading.distance_m, row["expected_distance_m"], places=2)

    def test_overload_readings_never_carry_distance(self):
        reading = self.engine.run_pipeline(
            adc_value=240,
            rc_ohms_per_m=0.01,
            source_node_id="overload-node",
            current_amps=self.engine.overload_threshold_amps + 0.25,
        )

        self.assertTrue(reading.is_overload)
        self.assertIsNone(reading.distance_m)


class LiveServer:
    def __init__(self, app):
        self.server = make_server("127.0.0.1", 0, app, threaded=True)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=2)


class Module1IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "fault_readings.sqlite3")
        self.app = create_app(
            {
                "TESTING": True,
                "MODULE1_DB_PATH": self.db_path,
                "MODULE1_START_BACKGROUND": True,
                "MODULE1_IDLE_INTERVAL_SECONDS": 0.15,
                "MODULE1_IDLE_SOURCE_NODE_ID": "idle-test",
            }
        )
        self.server = LiveServer(self.app)
        self.server.start()
        self.runtime = get_module1_runtime()

    def tearDown(self):
        self.runtime.stop_background_worker()
        self.server.stop()
        self.temp_dir.cleanup()

    def test_inject_fault_persists_and_broadcasts(self):
        source_node_id = "integration-source"
        message_queue: queue.Queue[dict] = queue.Queue()

        def listen_for_broadcast():
            async def _listen():
                websocket_url = f"ws://127.0.0.1:{self.server.port}/readings/stream"
                async with websockets.connect(websocket_url) as websocket:
                    deadline = time.time() + 5
                    while time.time() < deadline:
                        raw_message = await asyncio.wait_for(websocket.recv(), timeout=5)
                        payload = json.loads(raw_message)
                        if payload.get("source_node_id") == source_node_id:
                            message_queue.put(payload)
                            return
                    raise TimeoutError("Timed out waiting for the injected fault broadcast.")

            try:
                asyncio.run(_listen())
            except Exception as exc:
                message_queue.put({"error": str(exc)})

        listener_thread = threading.Thread(target=listen_for_broadcast, daemon=True)
        listener_thread.start()
        time.sleep(0.2)

        request_body = json.dumps(
            {
                "source_node_id": source_node_id,
                "target_distance_m": 468.5,
                "rc_ohms_per_m": 0.01,
                "overload": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.port}/simulate/inject-fault",
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 202)
            self.assertEqual(payload["status"], "queued")

        broadcast_payload = message_queue.get(timeout=6)
        listener_thread.join(timeout=1)
        self.assertNotIn("error", broadcast_payload)
        self.assertEqual(broadcast_payload["source_node_id"], source_node_id)
        self.assertFalse(broadcast_payload["is_overload"])

        deadline = time.time() + 5
        persisted_row = None
        while time.time() < deadline:
            connection = sqlite3.connect(self.db_path)
            try:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    """
                    SELECT adc_value, current_amps, distance_m, is_overload, source_node_id
                    FROM fault_readings
                    WHERE source_node_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (source_node_id,),
                ).fetchone()
            finally:
                connection.close()
            if row is not None:
                persisted_row = dict(row)
                break
            time.sleep(0.1)

        self.assertIsNotNone(persisted_row)
        self.assertEqual(persisted_row["source_node_id"], source_node_id)
        self.assertEqual(persisted_row["adc_value"], broadcast_payload["adc_value"])
        self.assertAlmostEqual(persisted_row["distance_m"], broadcast_payload["distance_m"], places=2)
        self.assertEqual(persisted_row["is_overload"], 0)


if __name__ == "__main__":
    unittest.main()

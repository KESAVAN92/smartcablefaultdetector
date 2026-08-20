import json
import os
import queue
import random
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, Flask, jsonify, request
from flask_sock import Sock

module1_bp = Blueprint("module1", __name__)

DEFAULT_PIPELINE_CURRENT_AMPS = 1.25 / 12
DEFAULT_RC_OHMS_PER_M = 0.01
ADC_REFERENCE_VOLTAGE = 5.0
ADC_RESOLUTION = 1024.0
ACS712_ZERO_CURRENT_VOLTAGE = 2.5
ACS712_SENSITIVITY_VOLTS_PER_AMP = 0.185
OVERLOAD_THRESHOLD_AMPS = 0.5
OVERLOAD_MARGIN_AMPS = 0.2
DEFAULT_IDLE_INTERVAL_SECONDS = 1.5
DEFAULT_IDLE_ADC_BASE = 4
DEFAULT_IDLE_ADC_NOISE = 3

sock = Sock()
module1_runtime = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_error(message: str, status_code: int = 422):
    return jsonify({"error": message}), status_code


def parse_json_body() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Request body must be valid JSON.")
    return payload


def require_number(payload: dict[str, Any], key: str, label: str) -> float:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"{label} is required.")
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a valid number.")

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a valid number.") from exc


def require_bool(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    raise ValueError(f"{key} must be a boolean.")


def require_source_node_id(payload: dict[str, Any]) -> str:
    value = payload.get("source_node_id")
    if value is None or str(value).strip() == "":
        raise ValueError("source_node_id is required.")
    return str(value).strip()


@dataclass
class FaultReading:
    adc_value: int
    current_amps: float
    voltage_x: float
    resistance_x: float
    distance_m: float | None
    is_overload: bool
    source_node_id: str
    recorded_at: str
    rc_ohms_per_m: float

    def to_record(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("rc_ohms_per_m", None)
        return payload


class FaultSimulationEngine:
    def __init__(
        self,
        *,
        pipeline_current_amps: float = DEFAULT_PIPELINE_CURRENT_AMPS,
        adc_reference_voltage: float = ADC_REFERENCE_VOLTAGE,
        adc_resolution: float = ADC_RESOLUTION,
        sensor_zero_voltage: float = ACS712_ZERO_CURRENT_VOLTAGE,
        sensor_sensitivity_volts_per_amp: float = ACS712_SENSITIVITY_VOLTS_PER_AMP,
        overload_threshold_amps: float = OVERLOAD_THRESHOLD_AMPS,
    ):
        self.pipeline_current_amps = pipeline_current_amps
        self.adc_reference_voltage = adc_reference_voltage
        self.adc_resolution = adc_resolution
        self.sensor_zero_voltage = sensor_zero_voltage
        self.sensor_sensitivity_volts_per_amp = sensor_sensitivity_volts_per_amp
        self.overload_threshold_amps = overload_threshold_amps

    def validate_adc(self, adc_value: float) -> int:
        if adc_value < 0 or adc_value > 1023:
            raise ValueError("ADC value must be between 0 and 1023.")

        adc_int = int(round(adc_value))
        if adc_int < 0 or adc_int > 1023:
            raise ValueError("ADC value must be between 0 and 1023.")
        return adc_int

    def validate_rc(self, rc_ohms_per_m: float) -> float:
        if rc_ohms_per_m <= 0:
            raise ValueError("Cable resistance per meter must be greater than 0.")
        return rc_ohms_per_m

    def validate_distance(self, distance_m: float) -> float:
        if distance_m < 0:
            raise ValueError("target_distance_m must be non-negative.")
        return distance_m

    def validate_resistance(self, resistance_ohms: float) -> float:
        if resistance_ohms < 0:
            raise ValueError("target_resistance_ohms must be non-negative.")
        return resistance_ohms

    def validate_current(self, current_amps: float) -> float:
        if current_amps <= 0:
            raise ValueError("Current must be greater than 0.")
        return current_amps

    def current_from_sensor_voltage(self, sensor_voltage: float) -> float:
        return abs(sensor_voltage - self.sensor_zero_voltage) / self.sensor_sensitivity_volts_per_amp

    def sensor_voltage_from_current(self, current_amps: float) -> float:
        current_amps = self.validate_current(current_amps)
        return self.sensor_zero_voltage + (current_amps * self.sensor_sensitivity_volts_per_amp)

    def run_pipeline(
        self,
        *,
        adc_value: float,
        rc_ohms_per_m: float,
        source_node_id: str,
        sensor_voltage: float | None = None,
        current_amps: float | None = None,
        recorded_at: str | None = None,
    ) -> FaultReading:
        adc_int = self.validate_adc(adc_value)
        rc_value = self.validate_rc(rc_ohms_per_m)

        if current_amps is None:
            if sensor_voltage is None:
                sensor_voltage = self.sensor_voltage_from_current(self.pipeline_current_amps)
            current_amps = self.current_from_sensor_voltage(sensor_voltage)
        else:
            current_amps = self.validate_current(current_amps)

        voltage_x = (adc_int * self.adc_reference_voltage) / self.adc_resolution
        resistance_x = voltage_x / self.pipeline_current_amps
        is_overload = current_amps > self.overload_threshold_amps
        distance_m = None if is_overload else (resistance_x / rc_value) / 2

        return FaultReading(
            adc_value=adc_int,
            current_amps=current_amps,
            voltage_x=voltage_x,
            resistance_x=resistance_x,
            distance_m=distance_m,
            is_overload=is_overload,
            source_node_id=source_node_id,
            recorded_at=recorded_at or utc_now_iso(),
            rc_ohms_per_m=rc_value,
        )

    def calculate_summary(
        self,
        *,
        adc_value: float,
        rc_ohms_per_m: float,
        current_amps: float,
    ) -> dict[str, Any]:
        current_value = self.validate_current(current_amps)
        adc_int = self.validate_adc(adc_value)
        rc_value = self.validate_rc(rc_ohms_per_m)
        voltage = (adc_int * self.adc_reference_voltage) / self.adc_resolution
        resistance = voltage / current_value
        distance = (resistance / rc_value) / 2
        return {
            "adc_value": adc_int,
            "voltage": voltage,
            "resistance": resistance,
            "distance": distance,
        }

    def inverse_adc_for_fault(
        self,
        *,
        rc_ohms_per_m: float,
        target_distance_m: float | None = None,
        target_resistance_ohms: float | None = None,
    ) -> int:
        rc_value = self.validate_rc(rc_ohms_per_m)
        provided_values = sum(value is not None for value in [target_distance_m, target_resistance_ohms])
        if provided_values != 1:
            raise ValueError("Provide exactly one of target_distance_m or target_resistance_ohms.")

        if target_distance_m is not None:
            resistance_x = self.validate_distance(target_distance_m) * rc_value * 2
        else:
            resistance_x = self.validate_resistance(target_resistance_ohms or 0)

        voltage_x = resistance_x * self.pipeline_current_amps
        adc_value = round((voltage_x * self.adc_resolution) / self.adc_reference_voltage)
        return self.validate_adc(adc_value)


class FaultReadingsRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        self._ensure_schema(connection)
        return connection

    def initialize(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection):
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fault_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                adc_value INTEGER NOT NULL,
                current_amps REAL NOT NULL,
                voltage_x REAL NOT NULL,
                resistance_x REAL NOT NULL,
                distance_m REAL,
                is_overload INTEGER NOT NULL,
                source_node_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """
        )

    def insert_reading(self, reading_payload: dict[str, Any]) -> dict[str, Any]:
        connection = self.connect()
        try:
            cursor = connection.execute(
                """
                INSERT INTO fault_readings (
                    adc_value,
                    current_amps,
                    voltage_x,
                    resistance_x,
                    distance_m,
                    is_overload,
                    source_node_id,
                    recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reading_payload["adc_value"],
                    reading_payload["current_amps"],
                    reading_payload["voltage_x"],
                    reading_payload["resistance_x"],
                    reading_payload["distance_m"],
                    1 if reading_payload["is_overload"] else 0,
                    reading_payload["source_node_id"],
                    reading_payload["recorded_at"],
                ),
            )
            connection.commit()
            return self.get_by_id(cursor.lastrowid)
        finally:
            connection.close()

    def get_by_id(self, row_id: int) -> dict[str, Any]:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM fault_readings WHERE id = ?",
                (row_id,),
            ).fetchone()
        finally:
            connection.close()
        return self._row_to_dict(row)

    def list_readings(self, *, limit: int = 50, source_node_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM fault_readings"
        params: list[Any] = []
        if source_node_id:
            query += " WHERE source_node_id = ?"
            params.append(source_node_id)

        query += " ORDER BY datetime(recorded_at) DESC, id DESC LIMIT ?"
        params.append(limit)

        connection = self.connect()
        try:
            rows = connection.execute(query, params).fetchall()
        finally:
            connection.close()

        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}

        return {
            "id": row["id"],
            "adc_value": row["adc_value"],
            "current_amps": row["current_amps"],
            "voltage_x": row["voltage_x"],
            "resistance_x": row["resistance_x"],
            "distance_m": row["distance_m"],
            "is_overload": bool(row["is_overload"]),
            "source_node_id": row["source_node_id"],
            "recorded_at": row["recorded_at"],
        }


class Module1Runtime:
    def __init__(self, app: Flask):
        self.app = app
        self.engine = FaultSimulationEngine(
            pipeline_current_amps=app.config["MODULE1_PIPELINE_CURRENT_AMPS"],
            overload_threshold_amps=app.config["MODULE1_OVERLOAD_THRESHOLD_AMPS"],
        )
        self.repository = FaultReadingsRepository(app.config["MODULE1_DB_PATH"])
        self.pending_faults: queue.Queue[dict[str, Any]] = queue.Queue()
        self.websocket_subscribers: list[queue.Queue[dict[str, Any]]] = []
        self.websocket_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self.sock_registered = False

    def register_websocket(self):
        if self.sock_registered:
            return

        @sock.route("/readings/stream")
        def readings_stream(ws):
            subscriber_queue: queue.Queue[dict[str, Any]] = queue.Queue()
            with self.websocket_lock:
                self.websocket_subscribers.append(subscriber_queue)

            try:
                while not self.stop_event.is_set():
                    try:
                        payload = subscriber_queue.get(timeout=1)
                    except queue.Empty:
                        continue
                    ws.send(json.dumps(payload))
            except Exception:
                pass
            finally:
                with self.websocket_lock:
                    if subscriber_queue in self.websocket_subscribers:
                        self.websocket_subscribers.remove(subscriber_queue)

        self.sock_registered = True

    def start_background_worker(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return

        if not self.app.config.get("MODULE1_START_BACKGROUND", True):
            return

        # Avoid duplicate workers from Flask's debug reloader parent process.
        if self.app.debug and os.environ.get("WERKZEUG_RUN_MAIN") not in {None, "true"}:
            return

        self.stop_event.clear()
        self.worker_thread = threading.Thread(
            target=self._background_loop,
            name="module1-reading-emitter",
            daemon=True,
        )
        self.worker_thread.start()

    def stop_background_worker(self):
        self.stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2)

    def enqueue_fault_reading(self, reading: FaultReading):
        self.pending_faults.put(reading.to_record())

    def generate_idle_reading(self) -> dict[str, Any]:
        base_adc = self.app.config["MODULE1_IDLE_ADC_BASE"]
        noise = self.app.config["MODULE1_IDLE_ADC_NOISE"]
        adc_value = max(0, min(1023, base_adc + random.randint(-noise, noise)))
        idle_current = max(
            0.001,
            self.engine.pipeline_current_amps + random.uniform(-0.01, 0.01),
        )
        reading = self.engine.run_pipeline(
            adc_value=adc_value,
            rc_ohms_per_m=self.app.config["MODULE1_DEFAULT_RC_OHMS_PER_M"],
            source_node_id=self.app.config["MODULE1_IDLE_SOURCE_NODE_ID"],
            current_amps=idle_current,
        )
        return reading.to_record()

    def persist_reading_via_internal_api(self, reading_payload: dict[str, Any]) -> dict[str, Any]:
        with self.app.test_client() as client:
            response = client.post(
                "/readings",
                json=reading_payload,
                headers={"X-Module1-Internal": "1"},
            )
            if response.status_code not in {200, 201}:
                raise RuntimeError(f"Internal POST /readings failed: {response.get_data(as_text=True)}")
            return response.get_json()

    def broadcast_reading(self, reading_payload: dict[str, Any]):
        with self.websocket_lock:
            subscribers = list(self.websocket_subscribers)

        for subscriber_queue in subscribers:
            subscriber_queue.put(reading_payload)

    def _background_loop(self):
        idle_interval = float(self.app.config["MODULE1_IDLE_INTERVAL_SECONDS"])
        while not self.stop_event.is_set():
            try:
                reading_payload = self.pending_faults.get(timeout=idle_interval)
            except queue.Empty:
                reading_payload = self.generate_idle_reading()

            persisted = self.persist_reading_via_internal_api(reading_payload)
            self.broadcast_reading(persisted)


def get_module1_runtime() -> Module1Runtime:
    if module1_runtime is None:
        raise RuntimeError("Module 1 runtime has not been initialized.")
    return module1_runtime


@module1_bp.get("/")
def get_module1():
    runtime = get_module1_runtime()
    return jsonify(
        {
            "module": "module1",
            "purpose": "Simulated fault-sensing engine and ingestion API",
            "status": "ready",
            "defaults": {
                "pipeline_current_amps": runtime.engine.pipeline_current_amps,
                "default_rc_ohms_per_m": DEFAULT_RC_OHMS_PER_M,
                "overload_threshold_amps": runtime.engine.overload_threshold_amps,
            },
            "routes": {
                "calculate": "/api/module1/calculate",
                "inject_fault": "/simulate/inject-fault",
                "create_reading": "/readings",
                "stream": "/readings/stream",
            },
        }
    )


@module1_bp.post("/calculate")
def calculate_module1():
    runtime = get_module1_runtime()
    try:
        payload = parse_json_body()
        result = runtime.engine.calculate_summary(
            adc_value=require_number(payload, "adc_value", "ADC value"),
            rc_ohms_per_m=require_number(
                payload,
                "rc_ohms_per_meter",
                "Cable resistance per meter",
            ),
            current_amps=require_number(payload, "current_amps", "Current"),
        )
    except ValueError as exc:
        return make_error(str(exc))

    return jsonify(result)


@module1_bp.get("/readings")
def list_readings():
    runtime = get_module1_runtime()
    source_node_id = request.args.get("source_node_id")
    readings = runtime.repository.list_readings(source_node_id=source_node_id)
    return jsonify({"items": readings})


@module1_bp.post("/readings")
def create_reading():
    runtime = get_module1_runtime()
    try:
        payload = parse_json_body()
        reading = {
            "adc_value": runtime.engine.validate_adc(require_number(payload, "adc_value", "ADC value")),
            "current_amps": runtime.engine.validate_current(
                require_number(payload, "current_amps", "Current")
            ),
            "voltage_x": require_number(payload, "voltage_x", "voltage_x"),
            "resistance_x": require_number(payload, "resistance_x", "resistance_x"),
            "distance_m": None
            if payload.get("distance_m") is None
            else float(payload.get("distance_m")),
            "is_overload": require_bool(payload, "is_overload"),
            "source_node_id": require_source_node_id(payload),
            "recorded_at": str(payload.get("recorded_at") or utc_now_iso()),
        }
        if reading["distance_m"] is not None and reading["distance_m"] < 0:
            raise ValueError("distance_m must be non-negative.")
        if reading["is_overload"]:
            reading["distance_m"] = None
    except ValueError as exc:
        return make_error(str(exc))

    stored = runtime.repository.insert_reading(reading)
    return jsonify(stored), 201


@module1_bp.post("/simulate/inject-fault")
def inject_fault():
    runtime = get_module1_runtime()
    try:
        payload = parse_json_body()
        source_node_id = require_source_node_id(payload)
        rc_ohms_per_m = payload.get("rc_ohms_per_m", payload.get("rc_ohms_per_meter", DEFAULT_RC_OHMS_PER_M))
        rc_value = runtime.engine.validate_rc(float(rc_ohms_per_m))
        overload = require_bool(payload, "overload", False)
        adc_value = runtime.engine.inverse_adc_for_fault(
            rc_ohms_per_m=rc_value,
            target_distance_m=payload.get("target_distance_m"),
            target_resistance_ohms=payload.get("target_resistance_ohms"),
        )
        current_amps = (
            runtime.engine.overload_threshold_amps + OVERLOAD_MARGIN_AMPS
            if overload
            else runtime.engine.pipeline_current_amps
        )
        reading = runtime.engine.run_pipeline(
            adc_value=adc_value,
            rc_ohms_per_m=rc_value,
            source_node_id=source_node_id,
            current_amps=current_amps,
        )
        runtime.enqueue_fault_reading(reading)
    except ValueError as exc:
        return make_error(str(exc))

    return (
        jsonify(
            {
                "status": "queued",
                "queued_reading": reading.to_record(),
            }
        ),
        202,
    )


def init_module1(app: Flask) -> Module1Runtime:
    global module1_runtime

    app.config.setdefault("MODULE1_DB_PATH", str(Path(app.root_path) / "module1_fault_readings.sqlite3"))
    app.config.setdefault("MODULE1_PIPELINE_CURRENT_AMPS", DEFAULT_PIPELINE_CURRENT_AMPS)
    app.config.setdefault("MODULE1_DEFAULT_RC_OHMS_PER_M", DEFAULT_RC_OHMS_PER_M)
    app.config.setdefault("MODULE1_OVERLOAD_THRESHOLD_AMPS", OVERLOAD_THRESHOLD_AMPS)
    app.config.setdefault("MODULE1_IDLE_INTERVAL_SECONDS", DEFAULT_IDLE_INTERVAL_SECONDS)
    app.config.setdefault("MODULE1_IDLE_ADC_BASE", DEFAULT_IDLE_ADC_BASE)
    app.config.setdefault("MODULE1_IDLE_ADC_NOISE", DEFAULT_IDLE_ADC_NOISE)
    app.config.setdefault("MODULE1_IDLE_SOURCE_NODE_ID", "idle-source")
    app.config.setdefault("MODULE1_START_BACKGROUND", True)

    sock.init_app(app)

    runtime = Module1Runtime(app)
    runtime.register_websocket()
    runtime.start_background_worker()
    module1_runtime = runtime
    return runtime

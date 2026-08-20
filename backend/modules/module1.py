from flask import Blueprint, jsonify, request

module1_bp = Blueprint("module1", __name__)

DEFAULT_CURRENT_AMPS = 1.25 / 12
ADC_REFERENCE_VOLTAGE = 5
ADC_RESOLUTION = 1024


def error_response(message: str, status_code: int = 422):
    return jsonify({"error": message}), status_code


def validate_number(value, name: str):
    if value is None:
        raise ValueError(f"{name} is required.")

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a valid number.") from exc


def calculate_fault_distance(adc_value: float, rc_ohms_per_meter: float, current_amps: float):
    if adc_value < 0 or adc_value > 1023:
        raise ValueError("ADC value must be between 0 and 1023.")

    if rc_ohms_per_meter <= 0:
        raise ValueError("Cable resistance per meter must be greater than 0.")

    if current_amps <= 0:
        raise ValueError("Current must be greater than 0.")

    voltage = (adc_value * ADC_REFERENCE_VOLTAGE) / ADC_RESOLUTION
    resistance = voltage / current_amps
    distance = (resistance / rc_ohms_per_meter) / 2

    return {
        "adc_value": adc_value,
        "voltage": voltage,
        "resistance": resistance,
        "distance": distance,
    }


@module1_bp.get("/")
def get_module1():
    return jsonify(
        {
            "module": "module1",
            "purpose": "Fault simulation and fault distance calculation",
            "status": "ready",
            "default_current_amps": DEFAULT_CURRENT_AMPS,
            "calculate_endpoint": "/api/module1/calculate",
        }
    )


@module1_bp.post("/calculate")
def calculate_module1():
    payload = request.get_json(silent=True)

    if not payload:
        return error_response("Request body must be valid JSON.")

    try:
        adc_value = validate_number(payload.get("adc_value"), "ADC value")
        rc_ohms_per_meter = validate_number(
            payload.get("rc_ohms_per_meter"), "Cable resistance per meter"
        )
        current_amps = validate_number(
            payload.get("current_amps", DEFAULT_CURRENT_AMPS), "Current"
        )
        result = calculate_fault_distance(adc_value, rc_ohms_per_meter, current_amps)
    except ValueError as exc:
        return error_response(str(exc))

    return jsonify(result)

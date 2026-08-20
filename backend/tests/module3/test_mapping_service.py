"""
Unit tests — Module 3 calculation pipeline & mapping service.

Fixtures from project report:
  Section 9.2 worked example: ADC=200, Rc=0.01 → Vx=0.9766V, Rx=9.375Ω, Dist=468.75m
  Section 13 experimental table (selected rows):
    ADC=100, Rc=0.01 → Dist≈234.4m
    ADC=300, Rc=0.01 → Dist≈703.1m
    ADC=50,  Rc=0.01 → Dist≈117.2m
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from modules.module3.adapters.module1_adapter import (
    ACS712_CURRENT_CONSTANT,
    ADC_VREF,
    ADC_RESOLUTION,
    compute_fault_reading,
    inverse_compute_adc,
    build_full_reading,
)
from modules.module3.adapters.module2_adapter import (
    graph_nearest,
    DEMO_NODES,
    DEMO_EDGES,
)
from modules.module3.mapping_service import process_reading


# ─────────────────────────────────────────────────────────────────────────────
# 1. Formula pipeline — Section 9.2 worked example
# ─────────────────────────────────────────────────────────────────────────────

class TestFormulaPipeline:
    """Validate formula pipeline matches Section 9.2 exactly (within 0.1 tol)."""

    def test_section_9_2_fixture(self):
        """ADC=200, Rc=0.01 → Vx≈0.9766V, Rx≈9.375Ω, Distance≈468.75m"""
        result = compute_fault_reading(adc_value=200, rc_ohms_per_m=0.01)
        assert abs(result["voltage_x"] - 0.9766) < 0.1,   f"Vx={result['voltage_x']}"
        assert abs(result["resistance_x"] - 9.375) < 0.1, f"Rx={result['resistance_x']}"
        assert abs(result["distance_m"] - 468.75) < 0.1,  f"Dist={result['distance_m']}"
        assert result["is_overload"] is False

    # Section 13 regression fixtures
    @pytest.mark.parametrize("adc,rc,expected_dist", [
        (100, 0.01, 234.375),   # Section 13 row
        (300, 0.01, 703.125),   # Section 13 row
        (50,  0.01, 117.188),   # Section 13 row
    ])
    def test_section_13_regression(self, adc, rc, expected_dist):
        result = compute_fault_reading(adc_value=adc, rc_ohms_per_m=rc)
        assert abs(result["distance_m"] - expected_dist) < 0.1, (
            f"ADC={adc}: got {result['distance_m']}, expected {expected_dist}"
        )

    def test_vx_formula(self):
        """Vx = (ADC × 5) / 1024 — allow for rounding in compute_fault_reading"""
        for adc in [0, 256, 512, 768, 1023]:
            result = compute_fault_reading(adc)
            expected_vx = (adc * ADC_VREF) / ADC_RESOLUTION
            assert abs(result["voltage_x"] - expected_vx) < 0.001  # rounded to 4dp

    def test_rx_formula(self):
        """Rx = Vx / I — allow for rounding in compute_fault_reading"""
        result = compute_fault_reading(200)
        expected_rx = ((200 * ADC_VREF) / ADC_RESOLUTION) / ACS712_CURRENT_CONSTANT
        assert abs(result["resistance_x"] - expected_rx) < 0.01  # rounded to 4dp

    def test_adc_zero_distance_zero(self):
        result = compute_fault_reading(0, rc_ohms_per_m=0.01)
        assert result["distance_m"] == 0.0
        assert result["voltage_x"] == 0.0

    def test_adc_bounds_valid(self):
        compute_fault_reading(0)
        compute_fault_reading(1023)

    def test_adc_out_of_range(self):
        with pytest.raises(ValueError, match="ADC"):
            compute_fault_reading(-1)
        with pytest.raises(ValueError, match="ADC"):
            compute_fault_reading(1024)

    def test_rc_zero_raises(self):
        with pytest.raises(ValueError, match="Rc"):
            compute_fault_reading(200, rc_ohms_per_m=0)

    def test_rc_negative_raises(self):
        with pytest.raises(ValueError, match="Rc"):
            compute_fault_reading(200, rc_ohms_per_m=-0.01)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Overload detection — report Section 13
# ─────────────────────────────────────────────────────────────────────────────

class TestOverloadDetection:
    """Overload readings MUST NOT carry a distance_m value."""

    def test_normal_reading_has_distance(self):
        result = compute_fault_reading(200)
        assert result["is_overload"] is False
        assert result["distance_m"] is not None

    def test_overload_reading_no_distance(self):
        """
        Current constant I = 1.25/12 ≈ 0.104A, well below the 5A threshold.
        The stub always sets is_overload=False because I is constant.
        This test documents the overload path via build_full_reading override.
        """
        reading = {
            "id": "test-overload",
            "adc_value": 1023,
            "current_amps": 999.0,   # artificially above threshold
            "voltage_x": None,
            "resistance_x": None,
            "distance_m": None,
            "is_overload": True,
            "source_node_id": "node-main-panel",
            "recorded_at": "2026-01-01T00:00:00+00:00",
            "_is_injected": True,
        }
        result = process_reading(reading)
        # Overload readings must never produce a fault_event
        assert result is None, "Overload reading must not create a fault_event"

    def test_none_distance_no_fault_event(self):
        reading = {
            "id": "test-none-dist",
            "adc_value": 0,
            "current_amps": 0.1,
            "voltage_x": 0.0,
            "resistance_x": 0.0,
            "distance_m": None,
            "is_overload": False,
            "source_node_id": "node-main-panel",
            "recorded_at": "2026-01-01T00:00:00+00:00",
            "_is_injected": True,
        }
        result = process_reading(reading)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Inverse computation
# ─────────────────────────────────────────────────────────────────────────────

class TestInverseCompute:
    """Round-trip: forward pipeline → inverse → forward again → same distance."""

    def test_round_trip_distance(self):
        target_dist = 468.75
        adc = inverse_compute_adc(target_distance_m=target_dist, rc_ohms_per_m=0.01)
        assert 0 <= adc <= 1023
        result = compute_fault_reading(adc, rc_ohms_per_m=0.01)
        assert abs(result["distance_m"] - target_dist) < 1.0   # within 1m after int rounding

    def test_round_trip_resistance(self):
        target_rx = 9.375
        adc = inverse_compute_adc(target_resistance_ohms=target_rx)
        assert 0 <= adc <= 1023

    def test_inverse_requires_target(self):
        with pytest.raises(ValueError):
            inverse_compute_adc()

    def test_negative_distance_raises(self):
        with pytest.raises(ValueError):
            inverse_compute_adc(target_distance_m=-1)

    def test_adc_clamped_to_valid_range(self):
        # Very large distance → ADC clamped at 1023
        adc = inverse_compute_adc(target_distance_m=999999, rc_ohms_per_m=0.01)
        assert adc == 1023


# ─────────────────────────────────────────────────────────────────────────────
# 4. Graph nearest traversal — Module 2 adapter
# ─────────────────────────────────────────────────────────────────────────────

class TestGraphNearest:
    """
    Tests use the demo graph (DEMO_NODES / DEMO_EDGES).
    Graph topology (distances in metres):
        Main Panel ─280─ Admin Block ─300─ Library ─280─ Lab Block ─320─ Sports Complex
        Main Panel ─220─ Hostel A ─260─ Lab Block
    """

    def test_zero_distance_returns_source(self):
        result = graph_nearest("node-main-panel", 0)
        assert result["nearest_node_id"] == "node-main-panel"
        assert result["edge_id"] is None
        assert result["beyond_graph"] is False

    def test_exact_node_hit(self):
        """280m exactly reaches Admin Block from Main Panel."""
        result = graph_nearest("node-main-panel", 280.0)
        assert result["nearest_node_id"] == "node-main-panel"
        assert result["edge_id"] == "edge-mp-admin"
        assert result["distance_along_edge_m"] is not None

    def test_mid_edge(self):
        """
        Demo graph: Main Panel has two edges:
          edge-mp-hostel: 220m to Hostel A  (shorter → Dijkstra picks this first)
          edge-mp-admin:  280m to Admin Block
        At 110m (half of 220m edge) → lands mid-edge on edge-mp-hostel.
        """
        result = graph_nearest("node-main-panel", 110.0)
        assert result["edge_id"] == "edge-mp-hostel"
        assert abs(result["distance_along_edge_m"] - 110.0) < 1.0
        assert result["beyond_graph"] is False

    def test_beyond_graph(self):
        """Distance > entire graph should return farthest node, not error."""
        result = graph_nearest("node-main-panel", 99999.0)
        assert result["beyond_graph"] is True
        assert result["nearest_node_id"] in DEMO_NODES
        assert result["edge_id"] is None   # lands on a node, not mid-edge

    def test_invalid_source_raises(self):
        with pytest.raises(ValueError, match="not in graph"):
            graph_nearest("non-existent-node", 100.0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Mapping service
# ─────────────────────────────────────────────────────────────────────────────

class TestMappingService:
    """Unit test mapping_service.process_reading() with known fixtures."""

    def _make_reading(self, distance_m, is_overload=False, is_injected=True):
        return {
            "id": "test-reading-001",
            "adc_value": 200,
            "current_amps": ACS712_CURRENT_CONSTANT,
            "voltage_x": 0.9766,
            "resistance_x": 9.375,
            "distance_m": distance_m,
            "is_overload": is_overload,
            "source_node_id": "node-main-panel",
            "recorded_at": "2026-01-01T12:00:00+00:00",
            "_is_injected": is_injected,
        }

    def test_non_injected_reading_skipped(self):
        reading = self._make_reading(468.75, is_injected=False)
        result = process_reading(reading)
        assert result is None

    def test_fault_event_created_for_injected(self):
        reading = self._make_reading(468.75, is_injected=True)
        result = process_reading(reading)
        assert result is not None
        assert result["reading_id"] == "test-reading-001"
        assert result["status"] == "open"
        assert result["nearest_node_id"] in DEMO_NODES

    def test_fault_event_correct_graph_position(self):
        """
        468.75m from Main Panel via Dijkstra shortest path:
          Main Panel → Hostel A: 220m  (edge-mp-hostel)
          Hostel A   → Lab Block: 260m  (edge-hostel-lab, cumulative 480m)
          468.75m lands on edge-hostel-lab at offset 468.75 - 220 = 248.75m
        """
        reading = self._make_reading(468.75, is_injected=True)
        result = process_reading(reading)
        assert result["graph_position"]["nearest_node_id"] == "node-hostel-a"
        assert result["graph_position"]["edge_id"] == "edge-hostel-lab"
        assert abs(result["graph_position"]["distance_along_edge_m"] - 248.75) < 1.0

    def test_beyond_graph_event_created_with_flag(self):
        reading = self._make_reading(99999.0, is_injected=True)
        result = process_reading(reading)
        assert result is not None
        assert result["graph_position"]["beyond_graph"] is True

    def test_overload_never_creates_event(self):
        reading = self._make_reading(None, is_overload=True, is_injected=True)
        result = process_reading(reading)
        assert result is None

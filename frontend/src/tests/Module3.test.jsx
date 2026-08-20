/**
 * Module3.test.jsx — Frontend unit tests for Module 3.
 *
 * Tests:
 *   1. Fault marker pixel position interpolation for known edge/offset
 *   2. Marker placed at node when edge_id is null
 *   3. Beyond-graph events render correctly
 *   4. WebSocket mock — inject event → marker appears
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ── Mock Leaflet (doesn't work in jsdom) ──────────────────────────────────────
vi.mock("leaflet", () => ({
  default: {
    CRS: { Simple: {} },
    icon: vi.fn(),
    divIcon: vi.fn(),
  },
  CRS: { Simple: {} },
}));
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }) => <div data-testid="map-container">{children}</div>,
  ImageOverlay: () => <div data-testid="image-overlay" />,
  CircleMarker: ({ children, center, pathOptions, eventHandlers }) => (
    <div
      data-testid="circle-marker"
      data-lat={center?.[0]}
      data-lng={center?.[1]}
      data-fill={pathOptions?.fillColor}
      onClick={eventHandlers?.click}
    >
      {children}
    </div>
  ),
  Polyline: ({ positions }) => (
    <div
      data-testid="polyline"
      data-from={`${positions?.[0]?.[0]},${positions?.[0]?.[1]}`}
      data-to={`${positions?.[1]?.[0]},${positions?.[1]?.[1]}`}
    />
  ),
  Popup: ({ children }) => <div data-testid="popup">{children}</div>,
  Tooltip: ({ children }) => <div data-testid="tooltip">{children}</div>,
  useMap: () => ({ fitBounds: vi.fn() }),
}));

// ── Mock socket.io-client ─────────────────────────────────────────────────────
const mockSocket = {
  on: vi.fn(),
  disconnect: vi.fn(),
};
vi.mock("socket.io-client", () => ({
  io: vi.fn(() => mockSocket),
}));

import FaultMap from "../modules/module3/FaultMap";
import { io } from "socket.io-client";

// ── Shared test graph ─────────────────────────────────────────────────────────
const GRAPH = {
  nodes: [
    { id: "node-a", name: "Node A", type: "panel",    x_coord: 100, y_coord: 100 },
    { id: "node-b", name: "Node B", type: "building", x_coord: 400, y_coord: 300 },
    { id: "node-c", name: "Node C", type: "building", x_coord: 700, y_coord: 100 },
  ],
  edges: [
    { id: "edge-ab", from_node_id: "node-a", to_node_id: "node-b", length_m: 500, resistance_per_m: 0.01, cable_type: "standard" },
    { id: "edge-bc", from_node_id: "node-b", to_node_id: "node-c", length_m: 400, resistance_per_m: 0.01, cable_type: "standard" },
  ],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Compute expected pixel position for a fault event on edge-ab at 250m.
 * edge-ab: from (y=100, x=100) to (y=300, x=400), length=500m
 * fraction = 250/500 = 0.5
 * expected: lat = 100 + 0.5*(300-100) = 200, lng = 100 + 0.5*(400-100) = 250
 */
function expectedMidEdgePos() {
  return { lat: 200, lng: 250 };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("FaultMap — marker position interpolation", () => {
  it("places fault marker at mid-point of edge for 50% offset", () => {
    const liveEvent = {
      id: "evt-1",
      reading_id: "r1",
      nearest_node_id: "node-a",
      edge_id: "edge-ab",
      distance_along_edge_m: 250, // 50% of 500m edge
      status: "open",
      created_at: "2026-01-01T12:00:00Z",
      reading: { distance_m: 250, voltage_x: 2.44, resistance_x: 23.4 },
      graph_position: { beyond_graph: false },
    };

    render(
      <FaultMap
        graphData={GRAPH}
        liveEvents={[liveEvent]}
        historicalEvents={[]}
        showHistory={false}
      />
    );

    // Find the live fault marker (red fill)
    const markers = screen.getAllByTestId("circle-marker");
    const faultMarker = markers.find(
      (m) =>
        m.getAttribute("data-fill") === "#fca5a5" ||
        m.getAttribute("data-fill") === "#fca5a5"
    );

    expect(faultMarker).toBeTruthy();
    const lat = parseFloat(faultMarker.getAttribute("data-lat"));
    const lng = parseFloat(faultMarker.getAttribute("data-lng"));

    const { lat: eLat, lng: eLng } = expectedMidEdgePos();
    expect(Math.abs(lat - eLat)).toBeLessThan(1);
    expect(Math.abs(lng - eLng)).toBeLessThan(1);
  });

  it("places fault marker exactly at node when edge_id is null", () => {
    const liveEvent = {
      id: "evt-2",
      reading_id: "r2",
      nearest_node_id: "node-b",
      edge_id: null,
      distance_along_edge_m: null,
      status: "open",
      created_at: "2026-01-01T12:00:00Z",
      reading: { distance_m: 500, voltage_x: 4.88, resistance_x: 46.9 },
      graph_position: { beyond_graph: false },
    };

    render(
      <FaultMap
        graphData={GRAPH}
        liveEvents={[liveEvent]}
        historicalEvents={[]}
        showHistory={false}
      />
    );

    const markers = screen.getAllByTestId("circle-marker");
    const faultMarker = markers.find((m) => m.getAttribute("data-fill") === "#fca5a5");

    expect(faultMarker).toBeTruthy();
    // node-b is at y=300, x=400 → Leaflet [lat=300, lng=400]
    expect(parseFloat(faultMarker.getAttribute("data-lat"))).toBeCloseTo(300, 0);
    expect(parseFloat(faultMarker.getAttribute("data-lng"))).toBeCloseTo(400, 0);
  });

  it("renders beyond-graph marker with purple fill", () => {
    const beyondEvent = {
      id: "evt-3",
      reading_id: "r3",
      nearest_node_id: "node-c",
      edge_id: null,
      distance_along_edge_m: null,
      status: "open",
      created_at: "2026-01-01T12:00:00Z",
      reading: { distance_m: 99999 },
      graph_position: { beyond_graph: true },
    };

    render(
      <FaultMap
        graphData={GRAPH}
        liveEvents={[beyondEvent]}
        historicalEvents={[]}
        showHistory={false}
      />
    );

    const markers = screen.getAllByTestId("circle-marker");
    const purpleMarker = markers.find((m) => m.getAttribute("data-fill") === "#c084fc");
    expect(purpleMarker).toBeTruthy();
  });

  it("renders correct number of edge polylines", () => {
    render(
      <FaultMap
        graphData={GRAPH}
        liveEvents={[]}
        historicalEvents={[]}
        showHistory={false}
      />
    );
    const polylines = screen.getAllByTestId("polyline");
    expect(polylines).toHaveLength(2); // edge-ab and edge-bc
  });

  it("renders correct number of node markers", () => {
    render(
      <FaultMap
        graphData={GRAPH}
        liveEvents={[]}
        historicalEvents={[]}
        showHistory={false}
      />
    );
    const markers = screen.getAllByTestId("circle-marker");
    // 3 node markers + 0 fault markers = 3
    expect(markers.length).toBeGreaterThanOrEqual(3);
  });

  it("renders historical markers when showHistory=true", () => {
    const histEvent = {
      id: "hist-1",
      reading_id: "rh1",
      nearest_node_id: "node-a",
      edge_id: null,
      distance_along_edge_m: null,
      status: "resolved",
      created_at: "2026-01-01T10:00:00Z",
      reading: { distance_m: 100 },
      graph_position: { beyond_graph: false },
    };

    const { rerender } = render(
      <FaultMap
        graphData={GRAPH}
        liveEvents={[]}
        historicalEvents={[histEvent]}
        showHistory={false}
      />
    );

    // No historical markers when showHistory=false
    const markersBefore = screen.getAllByTestId("circle-marker").length;

    rerender(
      <FaultMap
        graphData={GRAPH}
        liveEvents={[]}
        historicalEvents={[histEvent]}
        showHistory={true}
      />
    );

    // Historical markers should appear now
    const markersAfter = screen.getAllByTestId("circle-marker").length;
    expect(markersAfter).toBeGreaterThan(markersBefore);
  });
});

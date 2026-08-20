/**
 * FaultMap — Leaflet CRS.Simple map rendering the NEC layout with:
 *   • Node markers (color-coded by type)
 *   • Edge polylines
 *   • Live fault markers (red pulse) — interpolated on edges
 *   • Historical fault markers (faded) — toggled via showHistory
 *   • "Beyond mapped layout" indicator (purple)
 *   • Click-to-popup with full fault details
 */

import L from "leaflet";
import { useEffect } from "react";
import {
  CircleMarker,
  ImageOverlay,
  MapContainer,
  Polyline,
  Popup,
  Tooltip,
  useMap,
} from "react-leaflet";

// Image bounds — matches the demo graph coordinate space (1000 × 600 px)
const BOUNDS = [
  [0, 0],
  [600, 1000],
];

// Node type colours
const NODE_COLOR = {
  panel: "#ef4444",
  building: "#3b82f6",
  junction: "#94a3b8",
};

// ── Map auto-fit helper ────────────────────────────────────────────────────────
function FitBounds() {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(BOUNDS, { padding: [20, 20] });
  }, [map]);
  return null;
}

// ── Position helpers ───────────────────────────────────────────────────────────
function getFaultPosition(event, nodeMap, edgeMap) {
  if (event.edge_id && event.distance_along_edge_m != null) {
    const edge = edgeMap[event.edge_id];
    if (edge) {
      const from = nodeMap[edge.from_node_id];
      const to = nodeMap[edge.to_node_id];
      if (from && to) {
        const frac = Math.min(1, event.distance_along_edge_m / edge.length_m);
        return [
          from.y_coord + frac * (to.y_coord - from.y_coord),
          from.x_coord + frac * (to.x_coord - from.x_coord),
        ];
      }
    }
  }
  const node = nodeMap[event.nearest_node_id];
  return node ? [node.y_coord, node.x_coord] : null;
}

// ── Fault popup content ────────────────────────────────────────────────────────
function FaultPopup({ event, nodeMap, edgeMap }) {
  const node = nodeMap[event.nearest_node_id];
  const edge = event.edge_id ? edgeMap[event.edge_id] : null;
  const reading = event.reading || {};
  const beyond = event.graph_position?.beyond_graph;

  return (
    <div className="m3-popup" style={{ minWidth: 200 }}>
      <h4>
        {beyond ? "⚠️ Fault (Beyond Layout)" : "⚡ Cable Fault Detected"}
      </h4>
      <table>
        <tbody>
          <tr>
            <td>Distance</td>
            <td>
              {reading.distance_m != null
                ? `${reading.distance_m.toFixed(1)} m`
                : "—"}
            </td>
          </tr>
          <tr>
            <td>Nearest Node</td>
            <td>{node?.name ?? event.nearest_node_id}</td>
          </tr>
          {edge && (
            <tr>
              <td>Edge Offset</td>
              <td>{event.distance_along_edge_m?.toFixed(1)} m</td>
            </tr>
          )}
          <tr>
            <td>Voltage (Vx)</td>
            <td>
              {reading.voltage_x != null ? `${reading.voltage_x} V` : "—"}
            </td>
          </tr>
          <tr>
            <td>Resistance (Rx)</td>
            <td>
              {reading.resistance_x != null
                ? `${reading.resistance_x} Ω`
                : "—"}
            </td>
          </tr>
          <tr>
            <td>Status</td>
            <td style={{ textTransform: "capitalize" }}>{event.status}</td>
          </tr>
          <tr>
            <td>Time</td>
            <td>
              {event.created_at
                ? new Date(event.created_at).toLocaleTimeString()
                : "—"}
            </td>
          </tr>
        </tbody>
      </table>
      {beyond && (
        <div className="beyond-badge">⚠️ Distance exceeds mapped layout</div>
      )}
    </div>
  );
}

// ── Main FaultMap component ────────────────────────────────────────────────────
export default function FaultMap({
  graphData,
  liveEvents,
  historicalEvents,
  showHistory,
  onEventClick,
}) {
  const { nodes = [], edges = [] } = graphData;
  const nodeMap = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const edgeMap = Object.fromEntries(edges.map((e) => [e.id, e]));

  const layoutImageUrl =
    (import.meta.env.VITE_BACKEND_URL || "http://localhost:5000") +
    "/api/module3/layout-image";

  return (
    <MapContainer
      crs={L.CRS.Simple}
      bounds={BOUNDS}
      style={{ height: "100%", minHeight: 480, background: "#0f172a" }}
      zoomControl={true}
      attributionControl={false}
    >
      <FitBounds />

      {/* NEC layout chart image */}
      <ImageOverlay url={layoutImageUrl} bounds={BOUNDS} opacity={0.92} />

      {/* ── Cable edges ─────────────────────────────────────── */}
      {edges.map((edge) => {
        const from = nodeMap[edge.from_node_id];
        const to = nodeMap[edge.to_node_id];
        if (!from || !to) return null;
        return (
          <Polyline
            key={edge.id}
            positions={[
              [from.y_coord, from.x_coord],
              [to.y_coord, to.x_coord],
            ]}
            pathOptions={{
              color: "#60a5fa",
              weight: 3.5,
              opacity: 0.85,
              dashArray: undefined,
            }}
          >
            <Tooltip sticky>
              {edge.length_m}m · {edge.resistance_per_m} Ω/m · {edge.cable_type}
            </Tooltip>
          </Polyline>
        );
      })}

      {/* ── Nodes ───────────────────────────────────────────── */}
      {nodes.map((node) => (
        <CircleMarker
          key={node.id}
          center={[node.y_coord, node.x_coord]}
          radius={node.type === "panel" ? 10 : 7}
          pathOptions={{
            color: "#fff",
            weight: 2,
            fillColor: NODE_COLOR[node.type] || "#94a3b8",
            fillOpacity: 0.95,
          }}
        >
          <Tooltip permanent direction="top" offset={[0, -8]}>
            <span style={{ fontSize: 11, fontWeight: 700 }}>{node.name}</span>
          </Tooltip>
        </CircleMarker>
      ))}

      {/* ── Historical fault markers (faded) ────────────────── */}
      {showHistory &&
        historicalEvents.map((event) => {
          const pos = getFaultPosition(event, nodeMap, edgeMap);
          if (!pos) return null;
          const beyond = event.graph_position?.beyond_graph;
          return (
            <CircleMarker
              key={`hist-${event.id}`}
              center={pos}
              radius={7}
              pathOptions={{
                color: beyond ? "#a855f7" : "#94a3b8",
                weight: 1.5,
                fillColor: beyond ? "#d8b4fe" : "#cbd5e1",
                fillOpacity: 0.5,
              }}
              eventHandlers={{ click: () => onEventClick?.(event) }}
            >
              <Popup>
                <FaultPopup event={event} nodeMap={nodeMap} edgeMap={edgeMap} />
              </Popup>
            </CircleMarker>
          );
        })}

      {/* ── Live fault markers (animated red) ───────────────── */}
      {liveEvents.map((event) => {
        const pos = getFaultPosition(event, nodeMap, edgeMap);
        if (!pos) return null;
        const beyond = event.graph_position?.beyond_graph;
        return (
          <CircleMarker
            key={event.id}
            center={pos}
            radius={beyond ? 13 : 11}
            pathOptions={{
              color: beyond ? "#a855f7" : "#ef4444",
              weight: 3,
              fillColor: beyond ? "#c084fc" : "#fca5a5",
              fillOpacity: 0.92,
            }}
            eventHandlers={{ click: () => onEventClick?.(event) }}
          >
            <Popup>
              <FaultPopup event={event} nodeMap={nodeMap} edgeMap={edgeMap} />
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}

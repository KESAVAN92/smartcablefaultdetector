/**
 * Module 3 — Fault-to-Graph Mapping & Live Digital Map
 *
 * This is Module 3's entry point, replacing the placeholder.
 * All sub-components live in ./module3/ — teammates' modules are untouched.
 *
 * Data flow:
 *   Backend /api/module3/graph  →  useGraphData  →  FaultMap (nodes/edges)
 *   WS /fault-events            →  useFaultStream →  FaultMap (live markers)
 *   GET /api/module3/fault-events →  historicalEvents →  HistoryPanel + FaultMap
 *   POST /api/module3/simulate/inject-fault → InjectFaultPanel
 */

import { useCallback, useEffect, useState } from "react";
import FaultMap from "./module3/FaultMap";
import HistoryPanel from "./module3/HistoryPanel";
import InjectFaultPanel from "./module3/InjectFaultPanel";
import "./module3/module3.css";
import { useFaultStream } from "./module3/useFaultStream";
import { useGraphData } from "./module3/useGraphData";

const API = import.meta.env.VITE_BACKEND_URL
  ? `${import.meta.env.VITE_BACKEND_URL}/api/module3`
  : "/api/module3";

export default function Module3() {
  const { graphData, loading: graphLoading } = useGraphData();
  const { liveEvents, connected, clearEvents } = useFaultStream();
  const [historicalEvents, setHistoricalEvents] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);

  // Fetch historical events
  const fetchHistory = useCallback(() => {
    setLoadingHistory(true);
    fetch(`${API}/fault-events?limit=200`)
      .then((r) => r.json())
      .then((data) => {
        // Enrich with graph_position if present (set by mapping service)
        setHistoricalEvents(data);
      })
      .catch(console.error)
      .finally(() => setLoadingHistory(false));
  }, []);

  // Refresh history when a new live event arrives
  useEffect(() => {
    if (liveEvents.length > 0) {
      fetchHistory();
    }
  }, [liveEvents.length, fetchHistory]);

  // Initial history load
  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const handleEventClick = (event) => setSelectedEvent(event);

  const handleInjected = () => {
    setTimeout(fetchHistory, 500); // small delay for DB write
  };

  return (
    <div className="m3-page">
      {/* ── Header ─────────────────────────────────────────── */}
      <div className="m3-header">
        <h2 className="m3-title">
          🗺️ Live Fault Digital Map
        </h2>
        <div style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
          <span className={`m3-badge ${connected ? "connected" : "disconnected"}`}>
            <span className="dot" />
            {connected ? "WS Connected" : "WS Disconnected"}
          </span>
          <span className="m3-badge" style={{ background: "#e0f2fe", color: "#0369a1" }}>
            {liveEvents.length} live event{liveEvents.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* ── Body ───────────────────────────────────────────── */}
      <div className="m3-body">
        {/* MAP */}
        <div className="m3-map-wrap">
          {graphLoading ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 480, background: "#0f172a", color: "#60a5fa", fontSize: "1rem" }}>
              Loading cable layout…
            </div>
          ) : (
            <FaultMap
              graphData={graphData}
              liveEvents={liveEvents}
              historicalEvents={historicalEvents}
              showHistory={showHistory}
              onEventClick={handleEventClick}
            />
          )}

          {/* Map overlay controls */}
          <div className="m3-map-controls">
            <button
              className={`m3-ctrl-btn ${showHistory ? "active" : "primary"}`}
              onClick={() => { setShowHistory((v) => !v); if (!showHistory) fetchHistory(); }}
              title="Toggle historical faults on map"
            >
              📂 {showHistory ? "Hide History" : "Show History"}
            </button>
            <button
              className="m3-ctrl-btn primary"
              onClick={clearEvents}
              title="Clear live fault markers"
            >
              🗑️ Clear Live
            </button>
          </div>
        </div>

        {/* SIDEBAR */}
        <aside className="m3-sidebar">

          {/* Inject fault panel */}
          <div className="m3-panel">
            <h3>⚡ Inject Test Fault</h3>
            <InjectFaultPanel onInjected={handleInjected} />
          </div>

          {/* Fault event list */}
          <div className="m3-panel" style={{ flex: 1 }}>
            <h3 style={{ display: "flex", justifyContent: "space-between" }}>
              <span>Fault Events</span>
              {loadingHistory && <span style={{ fontSize: "0.7rem", color: "#94a3b8", fontWeight: 400 }}>refreshing…</span>}
            </h3>
            <HistoryPanel
              liveEvents={liveEvents}
              historicalEvents={historicalEvents}
              showHistory={showHistory}
              onEventClick={handleEventClick}
            />
          </div>

          {/* Legend */}
          <div className="m3-panel">
            <h3>Legend</h3>
            <div className="m3-legend">
              <div className="m3-legend-row">
                <span className="m3-legend-dot" style={{ background: "#ef4444" }} />
                Main Panel (node)
              </div>
              <div className="m3-legend-row">
                <span className="m3-legend-dot" style={{ background: "#3b82f6" }} />
                Building (node)
              </div>
              <div className="m3-legend-row">
                <span className="m3-legend-dot" style={{ background: "#94a3b8" }} />
                Junction (node)
              </div>
              <div className="m3-legend-row">
                <span className="m3-legend-dot" style={{ background: "#fca5a5", border: "2px solid #ef4444" }} />
                Live Fault Marker
              </div>
              <div className="m3-legend-row">
                <span className="m3-legend-dot" style={{ background: "#cbd5e1", border: "1.5px solid #94a3b8", opacity: 0.6 }} />
                Historical Fault (faded)
              </div>
              <div className="m3-legend-row">
                <span className="m3-legend-dot" style={{ background: "#d8b4fe", border: "2px solid #a855f7" }} />
                Beyond Mapped Layout
              </div>
            </div>
          </div>

        </aside>
      </div>
    </div>
  );
}

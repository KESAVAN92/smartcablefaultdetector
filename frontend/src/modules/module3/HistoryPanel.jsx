/**
 * HistoryPanel — shows live + historical fault events in a scrollable list.
 * Clicking an event scrolls the map to the fault marker.
 */

export default function HistoryPanel({ liveEvents, historicalEvents, showHistory, onEventClick }) {
  const allEvents = showHistory
    ? [...liveEvents, ...historicalEvents.filter((h) => !liveEvents.find((l) => l.id === h.id))]
    : liveEvents;

  const statusClass = (status, beyond) => {
    if (beyond) return "beyond";
    return status || "open";
  };

  const formatTime = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  return (
    <div className="m3-event-list">
      {allEvents.length === 0 && (
        <p className="m3-empty">No fault events yet.<br />Inject a fault to see it here.</p>
      )}
      {allEvents.map((event) => {
        const beyond = event.graph_position?.beyond_graph;
        const dist = event.reading?.distance_m;
        return (
          <div
            key={event.id}
            className={`m3-event-item ${statusClass(event.status, beyond)}`}
            onClick={() => onEventClick?.(event)}
            title="Click to highlight on map"
          >
            <div className="m3-event-dist">
              {dist != null ? `${dist.toFixed(1)} m` : "Overload"}
            </div>
            <div className="m3-event-meta">
              📍 {event.nearest_node_id?.replace("node-", "").replace(/-/g, " ")} ·{" "}
              {formatTime(event.created_at)}
            </div>
            {beyond && <div className="m3-event-beyond">⚠️ Beyond mapped layout</div>}
          </div>
        );
      })}
    </div>
  );
}

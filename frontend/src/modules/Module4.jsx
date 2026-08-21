import { useEffect, useState, useContext } from "react";
import ModuleCard from "../components/ModuleCard";
import { AuthContext } from "../auth";

export default function Module4() {
  const { token } = useContext(AuthContext);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);

  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [nodeId, setNodeId] = useState("");
  const [isOverload, setIsOverload] = useState("");

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (startDate) params.append("start", startDate);
        if (endDate) params.append("end", endDate);
        if (nodeId) params.append("node_id", nodeId);
        if (isOverload) params.append("is_overload", isOverload);
        
        const url = `/api/module4/reports/fault-history?${params.toString()}`;
        const res = await fetch(url, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        const json = await res.json();
        if (!mounted) return;
        setItems(json.items || []);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
    return () => (mounted = false);
  }, [token, startDate, endDate, nodeId, isOverload]);

  async function handleExport() {
    try {
      const params = new URLSearchParams({ format: "csv" });
      if (startDate) params.append("start", startDate);
      if (endDate) params.append("end", endDate);
      if (nodeId) params.append("node_id", nodeId);
      if (isOverload) params.append("is_overload", isOverload);

      const res = await fetch(`/api/module4/reports/fault-history?${params.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "fault-history.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      alert("Failed to export CSV");
    }
  }

  return (
    <ModuleCard title="Module 4 — Reports" summary="Fault history and exports">
      <div>
        <p>
          Use the filters in the API to narrow results. Click <strong>Export CSV</strong> to download.
        </p>

        <div style={{ marginBottom: 16, display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} placeholder="Start Date" />
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} placeholder="End Date" />
          <input type="text" value={nodeId} onChange={e => setNodeId(e.target.value)} placeholder="Node ID" />
          <select value={isOverload} onChange={e => setIsOverload(e.target.value)}>
            <option value="">Any</option>
            <option value="1">Overload Only</option>
            <option value="0">Fault Only</option>
          </select>
        </div>

        <div style={{ marginBottom: 12 }}>
          <button onClick={handleExport} className="btn-primary">Export CSV</button>
        </div>

        {loading && <div>Loading…</div>}
        {!loading && (
          <table className="table">
            <thead>
              <tr>
                <th>id</th>
                <th>reading_id</th>
                <th>distance_m</th>
                <th>is_overload</th>
                <th>status</th>
                <th>created_at</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id}>
                  <td>{it.id}</td>
                  <td>{it.reading_id}</td>
                  <td>{it.distance_m ?? "—"}</td>
                  <td>{it.is_overload ? "Yes" : "No"}</td>
                  <td>{it.status}</td>
                  <td>{it.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </ModuleCard>
  );
}

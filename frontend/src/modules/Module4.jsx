import { useEffect, useState, useContext } from "react";
import ModuleCard from "../components/ModuleCard";
import { AuthContext } from "../auth";

export default function Module4() {
  const { token } = useContext(AuthContext);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      try {
        const url = "/api/module4/reports/fault-history";
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
  }, [token]);

  return (
    <ModuleCard title="Module 4 — Reports" summary="Fault history and exports">
      <div>
        <p>
          Use the filters in the API to narrow results. Click <strong>Export CSV</strong> to download.
        </p>

        <div style={{ marginBottom: 12 }}>
          <a href="/api/module4/reports/fault-history?format=csv">Export CSV</a>
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

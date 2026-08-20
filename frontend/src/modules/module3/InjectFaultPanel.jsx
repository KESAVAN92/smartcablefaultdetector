/**
 * InjectFaultPanel — form to POST /api/module3/simulate/inject-fault.
 * Computes the inverse ADC so injected faults are identical to real readings.
 */

import { useState } from "react";

const API = import.meta.env.VITE_BACKEND_URL
  ? `${import.meta.env.VITE_BACKEND_URL}/api/module3`
  : "/api/module3";

// Demo graph node IDs (from module2_adapter.py DEMO_NODES)
const NODE_OPTIONS = [
  { id: "node-main-panel", label: "Main Panel" },
  { id: "node-admin-block", label: "Admin Block" },
  { id: "node-library", label: "Library" },
  { id: "node-lab-block", label: "Lab Block" },
  { id: "node-hostel-a", label: "Hostel A" },
  { id: "node-sports-complex", label: "Sports Complex" },
];

export default function InjectFaultPanel({ onInjected }) {
  const [sourceNode, setSourceNode] = useState("node-main-panel");
  const [distance, setDistance] = useState("300");
  const [rc, setRc] = useState("0.01");
  const [overload, setOverload] = useState(false);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const body = overload
        ? { source_node_id: sourceNode, overload: true }
        : {
            source_node_id: sourceNode,
            target_distance_m: parseFloat(distance),
            rc_ohms_per_m: parseFloat(rc),
          };

      const resp = await fetch(`${API}/simulate/inject-fault`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const data = await resp.json();

      if (!resp.ok) {
        showToast(data.error || `Error ${resp.status}`, "error");
        return;
      }

      if (overload) {
        showToast("⚡ Overload injected (no fault event — matches report §13)", "success");
      } else {
        const dist = data.reading?.distance_m?.toFixed(1);
        const adc = data.reading?.adc_value;
        showToast(`✅ Fault injected — ${dist}m (ADC=${adc})`, "success");
      }

      onInjected?.(data);
    } catch (err) {
      showToast(`Network error: ${err.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="m3-form" onSubmit={handleSubmit} id="inject-fault-form">
      <div>
        <label className="m3-label" htmlFor="inject-source-node">Source Node</label>
        <select
          id="inject-source-node"
          className="m3-select"
          value={sourceNode}
          onChange={(e) => setSourceNode(e.target.value)}
        >
          {NODE_OPTIONS.map((n) => (
            <option key={n.id} value={n.id}>{n.label}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="m3-label" htmlFor="inject-overload" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
          <input
            id="inject-overload"
            type="checkbox"
            checked={overload}
            onChange={(e) => setOverload(e.target.checked)}
          />
          Inject Overload (no distance)
        </label>
      </div>

      {!overload && (
        <>
          <div>
            <label className="m3-label" htmlFor="inject-distance">Target Distance (m)</label>
            <input
              id="inject-distance"
              className="m3-input"
              type="number"
              min="0"
              step="0.1"
              value={distance}
              onChange={(e) => setDistance(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="m3-label" htmlFor="inject-rc">Cable Rc (Ω/m)</label>
            <input
              id="inject-rc"
              className="m3-input"
              type="number"
              min="0.0001"
              step="0.001"
              value={rc}
              onChange={(e) => setRc(e.target.value)}
              required
            />
          </div>
        </>
      )}

      <button
        type="submit"
        className="m3-inject-btn"
        disabled={loading}
        id="inject-submit-btn"
      >
        {loading ? "Injecting…" : "⚡ Inject Fault"}
      </button>

      {toast && (
        <div className={`m3-toast ${toast.type}`}>{toast.msg}</div>
      )}
    </form>
  );
}

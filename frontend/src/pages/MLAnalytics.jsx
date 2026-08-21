import { useEffect, useState } from "react";

const API_ROOT = import.meta.env.VITE_API_URL || "http://localhost:5000";

export default function MLAnalytics() {
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_ROOT}/ml/analytics`)
      .then((response) => {
        if (!response.ok) throw new Error("Analytics are unavailable.");
        return response.json();
      })
      .then(setAnalytics)
      .catch((reason) => setError(reason.message));
  }, []);

  return (
    <div className="page-stack">
      <section className="hero">
        <p className="eyebrow">Predictive maintenance</p>
        <h2>ML analytics</h2>
        <p>Probabilistic estimates from the attached synthetic simulation dataset. Physical maintenance decisions require qualified inspection.</p>
      </section>
      {error && <p className="error-banner">{error}</p>}
      {analytics && (
        <>
          <section className="item-grid">
            <Metric label="Total predictions" value={analytics.total_predictions} />
            <Metric label="Known faults" value={analytics.known_faults} />
            <Metric label="Unknown anomalies" value={analytics.unknown_anomalies} />
            <Metric label="Average cable health" value={analytics.average_health == null ? "-" : `${analytics.average_health}/100`} />
          </section>
          <section className="panel">
            <div className="panel-header"><div><p className="eyebrow">Observed output</p><h2>Fault distribution</h2></div><span className="status-pill">{analytics.model_version}</span></div>
            <div className="item-grid">
              {Object.entries(analytics.fault_distribution).map(([fault, count]) => <Metric key={fault} label={fault.replaceAll("_", " ")} value={count} />)}
            </div>
            <p className="panel-copy">Selected runtime model: {analytics.selected_model || "configured ML model"}. Dataset provenance: {analytics.dataset}.</p>
          </section>
        </>
      )}
    </div>
  );
}

function Metric({ label, value }) {
  return <article className="item-card"><p className="eyebrow">{label}</p><h3>{value}</h3></article>;
}

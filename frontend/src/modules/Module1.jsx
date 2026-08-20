import { useState } from "react";

const defaultCurrent = 1.25 / 12;
const initialForm = {
  adcValue: "200",
  rcOhmsPerMeter: "0.01",
  currentAmps: defaultCurrent.toString()
};

function formatNumber(value, digits = 4) {
  return Number(value).toFixed(digits);
}

export default function Module1() {
  const [form, setForm] = useState(initialForm);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((currentForm) => ({ ...currentForm, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setResult(null);
    setIsSubmitting(true);

    try {
      const response = await fetch("http://127.0.0.1:5000/api/module1/calculate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          adc_value: form.adcValue,
          rc_ohms_per_meter: form.rcOhmsPerMeter,
          current_amps: form.currentAmps
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Calculation failed.");
      }

      setResult(data);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="page-stack">
      <section className="hero">
        <p className="eyebrow">Module 1</p>
        <h2>Fault Distance Simulator</h2>
        <p>
          Recreates the cable fault-distance calculation from the hardware
          prototype using ADC value, cable resistance per meter, and current.
        </p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Calculation Input</h2>
            <p className="panel-copy">
              Enter the measured ADC value, cable resistance per meter, and
              current to estimate the fault location.
            </p>
          </div>
          <span className="status-pill">API Connected</span>
        </div>

        <form
          onSubmit={handleSubmit}
          style={{ display: "grid", gap: "1rem", marginTop: "1.5rem" }}
        >
          <label style={{ display: "grid", gap: "0.35rem" }}>
            <span>ADC Value (0-1023)</span>
            <input
              name="adcValue"
              type="number"
              min="0"
              max="1023"
              step="1"
              value={form.adcValue}
              onChange={handleChange}
              style={inputStyle}
            />
          </label>

          <label style={{ display: "grid", gap: "0.35rem" }}>
            <span>Cable Resistance per Meter (Rc)</span>
            <input
              name="rcOhmsPerMeter"
              type="number"
              min="0.0000001"
              step="0.0001"
              value={form.rcOhmsPerMeter}
              onChange={handleChange}
              style={inputStyle}
            />
          </label>

          <label style={{ display: "grid", gap: "0.35rem" }}>
            <span>Current (A)</span>
            <input
              name="currentAmps"
              type="number"
              min="0.0000001"
              step="0.0001"
              value={form.currentAmps}
              onChange={handleChange}
              style={inputStyle}
            />
          </label>

          <button
            type="submit"
            disabled={isSubmitting}
            style={{
              ...buttonStyle,
              opacity: isSubmitting ? 0.7 : 1,
              cursor: isSubmitting ? "progress" : "pointer"
            }}
          >
            {isSubmitting ? "Calculating..." : "Calculate"}
          </button>
        </form>

        {error ? (
          <p
            style={{
              marginTop: "1rem",
              color: "#9f1239",
              fontWeight: 700
            }}
          >
            {error}
          </p>
        ) : null}
      </section>

      {result ? (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Result</h2>
              <p className="panel-copy">
                Computed using the same voltage, resistance, and distance
                equations from the project report.
              </p>
            </div>
            <span className="status-pill">Latest Run</span>
          </div>

          <div className="item-grid">
            <article className="item-card">
              <p>Voltage</p>
              <h3>{formatNumber(result.voltage)} V</h3>
            </article>
            <article className="item-card">
              <p>Resistance</p>
              <h3>{formatNumber(result.resistance)} Ohm</h3>
            </article>
            <article className="item-card">
              <p>Fault Distance</p>
              <h3>{formatNumber(result.distance, 2)} m</h3>
            </article>
          </div>
        </section>
      ) : null}
    </div>
  );
}

const inputStyle = {
  borderRadius: "14px",
  border: "1px solid rgba(20, 33, 61, 0.15)",
  padding: "0.9rem 1rem",
  fontSize: "1rem",
  background: "#fff"
};

const buttonStyle = {
  border: "none",
  borderRadius: "16px",
  background: "#fca311",
  color: "#14213d",
  fontWeight: 700,
  padding: "0.95rem 1.2rem",
  fontSize: "1rem"
};

export default function ModuleCard({ title, summary, items }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Module</p>
          <h2>{title}</h2>
        </div>
        <span className="status-pill">Ready</span>
      </div>
      <p className="panel-copy">{summary}</p>
      <div className="item-grid">
        {items.map((item) => (
          <article key={item.label} className="item-card">
            <h3>{item.label}</h3>
            <p>{item.value}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

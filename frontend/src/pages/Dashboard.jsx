import ModuleCard from "../components/ModuleCard";

const overviewItems = [
  { label: "Frontend", value: "React + Vite starter app" },
  { label: "Backend", value: "Python Flask API starter" },
  { label: "Modules", value: "4 frontend + 4 backend modules" },
  { label: "Status", value: "Ready for feature development" }
];

export default function Dashboard() {
  return (
    <div className="page-stack">
      <section className="hero">
        <p className="eyebrow">Project Starter</p>
        <h2>Frontend and backend foundations are in place.</h2>
        <p>
          Use each module area to build cable testing workflows, diagnostics,
          analytics, or reporting features.
        </p>
      </section>
      <ModuleCard
        title="System Overview"
        summary="This dashboard gives you a single place to expand the product structure as the app grows."
        items={overviewItems}
      />
    </div>
  );
}

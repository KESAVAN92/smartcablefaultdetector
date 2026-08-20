import ModuleCard from "../components/ModuleCard";

const items = [
  { label: "Focus", value: "Fault detection workflow" },
  { label: "UI Goal", value: "Collect readings and trigger analysis" },
  { label: "API Route", value: "/api/module2" }
];

export default function Module2() {
  return (
    <ModuleCard
      title="Module 2"
      summary="A placeholder workspace for the second frontend module."
      items={items}
    />
  );
}

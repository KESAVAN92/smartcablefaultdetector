import ModuleCard from "../components/ModuleCard";

const items = [
  { label: "Focus", value: "Historical diagnostics and logs" },
  { label: "UI Goal", value: "Visualize trends and prior inspections" },
  { label: "API Route", value: "/api/module3" }
];

export default function Module3() {
  return (
    <ModuleCard
      title="Module 3"
      summary="A placeholder workspace for the third frontend module."
      items={items}
    />
  );
}

import ModuleCard from "../components/ModuleCard";

const items = [
  { label: "Focus", value: "Reporting and exports" },
  { label: "UI Goal", value: "Prepare summaries and share results" },
  { label: "API Route", value: "/api/module4" }
];

export default function Module4() {
  return (
    <ModuleCard
      title="Module 4"
      summary="A placeholder workspace for the fourth frontend module."
      items={items}
    />
  );
}

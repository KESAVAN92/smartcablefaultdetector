import ModuleCard from "../components/ModuleCard";

const items = [
  { label: "Focus", value: "Cable registration and metadata" },
  { label: "UI Goal", value: "Track cable records and identifiers" },
  { label: "API Route", value: "/api/module1" }
];

export default function Module1() {
  return (
    <ModuleCard
      title="Module 1"
      summary="A placeholder workspace for the first frontend module."
      items={items}
    />
  );
}

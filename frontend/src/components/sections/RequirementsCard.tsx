import { Card } from "@/components/ui/Card";
import type { Requirements } from "@/types/api";

const FIELDS: { key: keyof Requirements; label: string }[] = [
  { key: "customer_name", label: "Customer name" },
  { key: "company_name", label: "Company" },
  { key: "requirement", label: "Requirement" },
  { key: "ro_capacity", label: "RO capacity" },
  { key: "location", label: "Location" },
  { key: "budget", label: "Budget" },
  { key: "timeline", label: "Timeline" },
  { key: "additional_requirements", label: "Additional requirements" },
];

export function RequirementsCard({ requirements }: { requirements: Requirements | null }) {
  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-foreground">Requirements</h2>
      {requirements ? (
        <dl className="grid grid-cols-1 gap-3 @sm:grid-cols-2">
          {FIELDS.map(({ key, label }) => (
            <div key={key}>
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="text-sm text-foreground">{requirements[key] || "—"}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-sm text-muted-foreground">
          No structured requirements were captured yet — this appears shortly after the call
          ends, once AI analysis finishes.
        </p>
      )}
    </Card>
  );
}

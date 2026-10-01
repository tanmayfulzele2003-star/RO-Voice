import { Card } from "@/components/ui/Card";
import type { ProfileField, Requirements } from "@/types/api";

/**
 * Collected requirements, labelled by the business profile the call ran
 * with. Values fill in live while the call is running (the agent saves each
 * one as it hears it) and are completed by post-call AI analysis.
 */
export function RequirementsCard({
  requirements,
  fields,
}: {
  requirements: Requirements | null;
  fields: ProfileField[];
}) {
  const values: Record<string, string> = requirements?.fields ?? {};
  // Show everything the profile asks for, plus anything collected under a key
  // the profile no longer has (e.g. the profile was edited after the call).
  const rows = [
    ...fields.map((f) => ({ key: f.key, label: f.label })),
    ...Object.keys(values)
      .filter((key) => !fields.some((f) => f.key === key))
      .map((key) => ({ key, label: key.replace(/_/g, " ") })),
  ];

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-foreground">Customer requirements</h2>
      {requirements ? (
        <dl className="grid grid-cols-1 gap-3 @sm:grid-cols-2">
          {rows.map(({ key, label }) => (
            <div key={key}>
              <dt className="text-xs capitalize text-muted-foreground">{label}</dt>
              <dd className="text-sm text-foreground">{values[key] || "—"}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-sm text-muted-foreground">
          No requirements were captured yet — they fill in during the call and are completed by
          AI analysis shortly after it ends.
        </p>
      )}
    </Card>
  );
}

import { Card } from "@/components/ui/Card";
import { LeadStatusBadge } from "@/components/ui/Badge";
import type { CallSummary } from "@/types/api";

export function SummaryCard({ summary }: { summary: CallSummary | null }) {
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">AI Summary</h2>
        {summary?.lead_status ? <LeadStatusBadge status={summary.lead_status} /> : null}
      </div>
      {summary ? (
        <div className="flex flex-col gap-3 text-sm text-foreground">
          <p>{summary.summary ?? "No summary text available."}</p>
          {summary.customer_intent ? (
            <p>
              <span className="font-medium">Intent: </span>
              {summary.customer_intent}
            </p>
          ) : null}
          {summary.key_requirements && summary.key_requirements.length > 0 ? (
            <div>
              <p className="font-medium">Key requirements</p>
              <ul className="list-disc pl-5">
                {summary.key_requirements.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {summary.important_points && summary.important_points.length > 0 ? (
            <div>
              <p className="font-medium">Important points</p>
              <ul className="list-disc pl-5">
                {summary.important_points.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <p>
            <span className="font-medium">Follow-up required: </span>
            {summary.follow_up === null || summary.follow_up === undefined
              ? "Unknown"
              : summary.follow_up
                ? "Yes"
                : "No"}
          </p>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          AI analysis hasn&apos;t completed yet — it runs automatically shortly after the call
          ends.
        </p>
      )}
    </Card>
  );
}

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageShell } from "@/components/layout/PageShell";
import { CallStatusBadge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { RequirementsCard } from "@/components/sections/RequirementsCard";
import { SummaryCard } from "@/components/sections/SummaryCard";
import { TranscriptView } from "@/components/sections/TranscriptView";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import { formatDateTime, formatDuration, formatPhone } from "@/lib/formatters";
import type { CallDetail } from "@/types/api";

export const metadata: Metadata = {
  title: "Call detail",
};

export default async function CallDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let call: CallDetail | null = null;
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    call = await apiClient.getCall(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load call.";
  }

  if (loadError || !call) {
    return (
      <PageShell title="Call detail">
        <ErrorState message={loadError ?? "Failed to load call."} />
      </PageShell>
    );
  }

  return (
    <PageShell
      title={call.customer_name}
      description={`${formatPhone(call.customer_phone)} · ${formatDateTime(call.created_at)}`}
      actions={<CallStatusBadge status={call.status} />}
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <p className="text-xs text-muted-foreground">Direction</p>
          <p className="mt-1 text-sm font-medium capitalize text-foreground">{call.direction}</p>
        </Card>
        <Card>
          <p className="text-xs text-muted-foreground">Duration</p>
          <p className="mt-1 text-sm font-medium text-foreground">
            {formatDuration(call.duration_seconds)}
          </p>
        </Card>
        <Card>
          <p className="text-xs text-muted-foreground">Started</p>
          <p className="mt-1 text-sm font-medium text-foreground">
            {formatDateTime(call.start_time)}
          </p>
        </Card>
        <Card>
          <p className="text-xs text-muted-foreground">Error reason</p>
          <p className="mt-1 text-sm font-medium text-foreground">{call.error_reason ?? "—"}</p>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SummaryCard summary={call.summary} />
        <RequirementsCard requirements={call.requirements} />
      </div>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-foreground">Transcript</h2>
        <TranscriptView messages={call.messages} />
      </Card>
    </PageShell>
  );
}

import type { ReactNode } from "react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageShell } from "@/components/layout/PageShell";
import { AutoRefresh } from "@/components/sections/AutoRefresh";
import { CallEventsTimeline } from "@/components/sections/CallEventsTimeline";
import { CallStatusBadge, ChannelBadge, OutcomeBadge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { RequirementsCard } from "@/components/sections/RequirementsCard";
import { SummaryCard } from "@/components/sections/SummaryCard";
import { TranscriptView } from "@/components/sections/TranscriptView";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import { formatDateTime, formatDuration, formatPhone, formatStatusLabel } from "@/lib/formatters";
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

  const isLive = ["queued", "ringing", "in_progress"].includes(call.status);
  // Post-call analysis runs right after the call; poll for it for a while.
  const analysisPending =
    !isLive &&
    !call.summary?.summary &&
    call.messages.length > 0 &&
    !call.events.some((e) => e.event_type === "analysis_failed");
  const followUp = call.summary?.follow_up;

  const info: { label: string; value: ReactNode }[] = [
    { label: "Outcome", value: <OutcomeBadge outcome={call.outcome} /> },
    {
      label: "Follow-up",
      value: followUp == null ? "—" : followUp ? "Required" : "Not required",
    },
    { label: "Duration", value: formatDuration(call.duration_seconds) },
    { label: "Started", value: formatDateTime(call.start_time) },
    { label: "Ended", value: formatDateTime(call.end_time) },
    {
      label: "Channel",
      value: (
        <span className="flex items-center gap-2">
          <ChannelBadge channel={call.channel} />
          <span className="capitalize">{call.direction}</span>
        </span>
      ),
    },
    { label: "Business", value: call.profile_name ?? "—" },
    { label: "Error reason", value: call.error_reason ? formatStatusLabel(call.error_reason) : "—" },
  ];
  const context = [
    call.customer_company && `Company: ${call.customer_company}`,
    call.customer_purpose && `Purpose: ${call.customer_purpose}`,
    call.customer_product && `Product: ${call.customer_product}`,
  ].filter(Boolean);

  return (
    <PageShell
      title={call.customer_name}
      description={`${formatPhone(call.customer_phone)} · ${formatDateTime(call.created_at)}${
        context.length ? ` · ${context.join(" · ")}` : ""
      }`}
      actions={<CallStatusBadge status={call.status} />}
    >
      <AutoRefresh
        active={isLive || analysisPending}
        stopAfter={isLive ? undefined : (call.end_time ?? call.created_at)}
      />
      {isLive || analysisPending ? (
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {isLive
            ? "Call in progress — this page updates automatically."
            : "Generating the AI summary — this page updates automatically."}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {info.map((item) => (
          <Card key={item.label}>
            <p className="text-xs text-muted-foreground">{item.label}</p>
            <div className="mt-1 text-sm font-medium text-foreground">{item.value}</div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SummaryCard summary={call.summary} />
        <RequirementsCard requirements={call.requirements} fields={call.profile_fields} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-foreground">Transcript</h2>
          <TranscriptView messages={call.messages} />
        </Card>
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-foreground">Call events</h2>
          <CallEventsTimeline events={call.events} />
        </Card>
      </div>
    </PageShell>
  );
}

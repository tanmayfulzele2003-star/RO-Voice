import type { ReactNode } from "react";

type Tone = "success" | "danger" | "warning" | "info" | "neutral";

const toneClasses: Record<Tone, string> = {
  success: "bg-success-muted text-success-muted-foreground",
  danger: "bg-danger-muted text-danger-muted-foreground",
  warning: "bg-warning-muted text-warning-muted-foreground",
  info: "bg-info-muted text-info-muted-foreground",
  neutral: "bg-muted text-muted-foreground",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${toneClasses[tone]}`}
    >
      {children}
    </span>
  );
}

const CALL_STATUS_TONE: Record<string, Tone> = {
  completed: "success",
  in_progress: "info",
  ringing: "info",
  queued: "neutral",
  failed: "danger",
  no_answer: "warning",
  disconnected: "warning",
};

const CALL_STATUS_LABEL: Record<string, string> = {
  in_progress: "In progress",
  no_answer: "No answer",
};

export function CallStatusBadge({ status }: { status: string }) {
  const label = CALL_STATUS_LABEL[status] ?? status.charAt(0).toUpperCase() + status.slice(1);
  return <Badge tone={CALL_STATUS_TONE[status] ?? "neutral"}>{label}</Badge>;
}

const LEAD_STATUS_TONE: Record<string, Tone> = {
  interested: "success",
  not_interested: "danger",
  uncertain: "warning",
};

const LEAD_STATUS_LABEL: Record<string, string> = {
  interested: "Interested",
  not_interested: "Not interested",
  uncertain: "Uncertain",
};

export function LeadStatusBadge({ status }: { status: string | null }) {
  if (!status) return <Badge tone="neutral">Unknown</Badge>;
  return <Badge tone={LEAD_STATUS_TONE[status] ?? "neutral"}>{LEAD_STATUS_LABEL[status] ?? status}</Badge>;
}

const OUTCOME_TONE: Record<string, Tone> = {
  qualified: "success",
  not_interested: "danger",
  callback: "warning",
  incomplete: "neutral",
  no_answer: "warning",
  no_conversation: "neutral",
  failed: "danger",
};

export const OUTCOME_LABEL: Record<string, string> = {
  qualified: "Qualified lead",
  not_interested: "Not interested",
  callback: "Call back",
  incomplete: "Incomplete",
  no_answer: "No answer",
  no_conversation: "No conversation",
  failed: "Failed",
};

export function OutcomeBadge({ outcome }: { outcome: string | null }) {
  if (!outcome) return <Badge tone="neutral">Pending</Badge>;
  return <Badge tone={OUTCOME_TONE[outcome] ?? "neutral"}>{OUTCOME_LABEL[outcome] ?? outcome}</Badge>;
}

export function ChannelBadge({ channel }: { channel: string }) {
  return <Badge tone="info">{channel === "browser" ? "Browser" : "Phone"}</Badge>;
}

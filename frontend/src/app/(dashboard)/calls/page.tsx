import Link from "next/link";
import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { CallsFilterBar } from "@/components/sections/CallsFilterBar";
import { CallStatusBadge, ChannelBadge, LeadStatusBadge, OutcomeBadge } from "@/components/ui/Badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { ApiError, type CallListFilters } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import { formatDateTime, formatDuration, formatPhone } from "@/lib/formatters";
import type { BusinessProfile, CallListItem } from "@/types/api";

export const metadata: Metadata = {
  title: "Calls",
  description: "History of every call the AI agent has placed or received.",
};

const PAGE_SIZE = 20;

type CallsSearchParams = {
  offset?: string;
  status?: string;
  lead_status?: string;
  date_from?: string;
  date_to?: string;
  customer_name?: string;
  follow_up?: string;
  outcome?: string;
  channel?: string;
  profile_id?: string;
};

const FILTER_KEYS = [
  "status",
  "lead_status",
  "date_from",
  "date_to",
  "customer_name",
  "follow_up",
  "outcome",
  "channel",
  "profile_id",
] as const;

export default async function CallsPage({
  searchParams,
}: {
  searchParams: Promise<CallsSearchParams>;
}) {
  const params = await searchParams;
  const offset = Math.max(0, Number(params.offset ?? 0) || 0);

  const filters: CallListFilters = { limit: PAGE_SIZE, offset };
  for (const key of FILTER_KEYS) {
    filters[key] = params[key] || undefined;
  }
  const filtersActive = FILTER_KEYS.some((key) => Boolean(filters[key]));

  let items: CallListItem[] = [];
  let total = 0;
  let profiles: BusinessProfile[] = [];
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    const [result, profileList] = await Promise.all([
      apiClient.listCalls(filters),
      apiClient.listProfiles(),
    ]);
    items = result.items;
    total = result.total;
    profiles = profileList;
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load calls.";
  }

  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;
  const pageQuery = (nextOffset: number) => {
    const usp = new URLSearchParams();
    usp.set("offset", String(nextOffset));
    for (const key of FILTER_KEYS) {
      const value = filters[key];
      if (value) usp.set(key, String(value));
    }
    return `/calls?${usp.toString()}`;
  };

  return (
    <PageShell title="Calls" description={`${total} call${total === 1 ? "" : "s"} on record.`}>
      <CallsFilterBar profiles={profiles.map((p) => ({ id: p.id, name: p.name }))} />

      {loadError ? (
        <ErrorState message={loadError} />
      ) : items.length === 0 ? (
        <EmptyState
          title={filtersActive ? "No calls match these filters" : "No calls yet"}
          description={
            filtersActive
              ? "Try widening the date range or clearing a filter."
              : "Start a call from the Customers page to see it here."
          }
        />
      ) : (
        <>
          <Table>
            <THead>
              <TR>
                <TH>Customer</TH>
                <TH>Phone</TH>
                <TH>Date</TH>
                <TH>Duration</TH>
                <TH>Status</TH>
                <TH>Outcome</TH>
                <TH>Lead</TH>
                <TH>Follow-up</TH>
                <TH>Channel</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((call) => (
                <TR key={call.id}>
                  <TD>
                    <Link
                      href={`/calls/${call.id}`}
                      className="font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                    >
                      {call.customer_name}
                    </Link>
                    {profiles.length > 1 && call.profile_name ? (
                      <p className="text-xs text-muted-foreground">{call.profile_name}</p>
                    ) : null}
                  </TD>
                  <TD>{formatPhone(call.customer_phone)}</TD>
                  <TD>{formatDateTime(call.start_time ?? call.created_at)}</TD>
                  <TD>{formatDuration(call.duration_seconds)}</TD>
                  <TD>
                    <CallStatusBadge status={call.status} />
                  </TD>
                  <TD>
                    <OutcomeBadge outcome={call.outcome} />
                  </TD>
                  <TD>
                    <LeadStatusBadge status={call.lead_status} />
                  </TD>
                  <TD>{call.follow_up == null ? "—" : call.follow_up ? "Yes" : "No"}</TD>
                  <TD>
                    <ChannelBadge channel={call.channel} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <div className="flex justify-end gap-2">
            <Link
              aria-disabled={!hasPrev}
              href={hasPrev ? pageQuery(offset - PAGE_SIZE) : pageQuery(0)}
              className={`rounded-lg border border-border px-3 py-1.5 text-sm ${
                hasPrev ? "hover:bg-muted" : "pointer-events-none opacity-50"
              }`}
            >
              Previous
            </Link>
            <Link
              aria-disabled={!hasNext}
              href={pageQuery(offset + PAGE_SIZE)}
              className={`rounded-lg border border-border px-3 py-1.5 text-sm ${
                hasNext ? "hover:bg-muted" : "pointer-events-none opacity-50"
              }`}
            >
              Next
            </Link>
          </div>
        </>
      )}
    </PageShell>
  );
}

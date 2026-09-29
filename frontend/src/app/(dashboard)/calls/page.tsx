import Link from "next/link";
import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { CallsFilterBar } from "@/components/sections/CallsFilterBar";
import { CallStatusBadge, LeadStatusBadge } from "@/components/ui/Badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { ApiError, type CallListFilters } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import { formatDateTime, formatDuration } from "@/lib/formatters";
import type { CallListItem } from "@/types/api";

export const metadata: Metadata = {
  title: "Calls",
  description: "History of every call the RO sales agent has placed or received.",
};

const PAGE_SIZE = 20;

type CallsSearchParams = {
  offset?: string;
  status?: string;
  lead_status?: string;
  date_from?: string;
  date_to?: string;
  customer_name?: string;
};

export default async function CallsPage({
  searchParams,
}: {
  searchParams: Promise<CallsSearchParams>;
}) {
  const params = await searchParams;
  const offset = Math.max(0, Number(params.offset ?? 0) || 0);

  const filters: CallListFilters = {
    limit: PAGE_SIZE,
    offset,
    status: params.status || undefined,
    lead_status: params.lead_status || undefined,
    date_from: params.date_from || undefined,
    date_to: params.date_to || undefined,
    customer_name: params.customer_name || undefined,
  };
  const filtersActive = Boolean(
    filters.status || filters.lead_status || filters.date_from || filters.date_to || filters.customer_name,
  );

  let items: CallListItem[] = [];
  let total = 0;
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    const result = await apiClient.listCalls(filters);
    items = result.items;
    total = result.total;
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load calls.";
  }

  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;
  const pageQuery = (nextOffset: number) => {
    const usp = new URLSearchParams();
    usp.set("offset", String(nextOffset));
    if (filters.status) usp.set("status", filters.status);
    if (filters.lead_status) usp.set("lead_status", filters.lead_status);
    if (filters.date_from) usp.set("date_from", filters.date_from);
    if (filters.date_to) usp.set("date_to", filters.date_to);
    if (filters.customer_name) usp.set("customer_name", filters.customer_name);
    return `/calls?${usp.toString()}`;
  };

  return (
    <PageShell title="Calls" description={`${total} call${total === 1 ? "" : "s"} on record.`}>
      <CallsFilterBar />

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
                <TH>Direction</TH>
                <TH>Status</TH>
                <TH>Lead</TH>
                <TH>Duration</TH>
                <TH>Started</TH>
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
                  </TD>
                  <TD className="capitalize">{call.direction}</TD>
                  <TD>
                    <CallStatusBadge status={call.status} />
                  </TD>
                  <TD>
                    <LeadStatusBadge status={call.lead_status} />
                  </TD>
                  <TD>{formatDuration(call.duration_seconds)}</TD>
                  <TD>{formatDateTime(call.start_time ?? call.created_at)}</TD>
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

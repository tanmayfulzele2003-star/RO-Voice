import Link from "next/link";
import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { AutoRefresh } from "@/components/sections/AutoRefresh";
import { CampaignStatusBadge } from "@/components/ui/Badge";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { formatDateTime } from "@/lib/formatters";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { Campaign } from "@/types/api";

export const metadata: Metadata = {
  title: "Campaigns",
  description: "Call a list of customers in parallel, with automatic retries.",
};

const LINK_CLASS =
  "font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

export default async function CampaignsPage() {
  let campaigns: Campaign[] = [];
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    campaigns = await apiClient.listCampaigns();
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load campaigns.";
  }

  return (
    <PageShell
      title="Campaigns"
      description="The dialer calls a campaign's customers several at a time and retries the ones who don't answer."
      actions={
        <Link
          href="/campaigns/new"
          className="inline-flex items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          New campaign
        </Link>
      }
    >
      <AutoRefresh active={campaigns.some((c) => c.status === "running")} intervalMs={5000} />
      {loadError ? (
        <ErrorState message={loadError} />
      ) : campaigns.length === 0 ? (
        <EmptyState
          title="No campaigns yet"
          description="Create one to call a list of customers at once."
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Campaign</TH>
              <TH>Status</TH>
              <TH>Progress</TH>
              <TH>On a call now</TH>
              <TH>Lines</TH>
              <TH>Created</TH>
            </TR>
          </THead>
          <TBody>
            {campaigns.map((c) => {
              const done = c.counts.completed + c.counts.failed + c.counts.cancelled;
              return (
                <TR key={c.id}>
                  <TD>
                    <Link href={`/campaigns/${c.id}`} className={LINK_CLASS}>
                      {c.name}
                    </Link>
                  </TD>
                  <TD>
                    <CampaignStatusBadge status={c.status} />
                    {c.status_reason ? (
                      <p className="mt-1 text-xs text-muted-foreground">Needs attention</p>
                    ) : null}
                  </TD>
                  <TD>
                    {done} / {c.counts.total}
                    {c.counts.failed ? (
                      <span className="text-muted-foreground"> · {c.counts.failed} unreachable</span>
                    ) : null}
                  </TD>
                  <TD>{c.counts.dialing}</TD>
                  <TD>{c.max_concurrent}</TD>
                  <TD>{formatDateTime(c.created_at)}</TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      )}
    </PageShell>
  );
}

import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageShell } from "@/components/layout/PageShell";
import { AutoRefresh } from "@/components/sections/AutoRefresh";
import { CampaignControls } from "@/components/sections/CampaignControls";
import { CampaignStatusBadge, ContactStatusBadge, OUTCOME_LABEL } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { formatDateTime, formatPhone, formatStatusLabel } from "@/lib/formatters";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { CampaignDetail } from "@/types/api";

export const metadata: Metadata = {
  title: "Campaign",
};

const LINK_CLASS =
  "text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

export default async function CampaignPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let campaign: CampaignDetail | null = null;
  let profileName: string | null = null;
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    campaign = await apiClient.getCampaign(id);
    if (campaign.profile_id) {
      const profiles = await apiClient.listProfiles();
      profileName = profiles.find((p) => p.id === campaign?.profile_id)?.name ?? null;
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load campaign.";
  }

  if (loadError || !campaign) {
    return (
      <PageShell title="Campaign">
        <ErrorState message={loadError ?? "Failed to load campaign."} />
      </PageShell>
    );
  }

  const { counts } = campaign;
  const tiles = [
    { label: "Customers", value: counts.total },
    { label: "Waiting", value: counts.pending },
    { label: "On a call now", value: counts.dialing },
    { label: "Done", value: counts.completed },
    { label: "Unreachable", value: counts.failed },
  ];
  const settings = [
    `${campaign.max_concurrent} call${campaign.max_concurrent === 1 ? "" : "s"} at once`,
    `up to ${campaign.max_attempts} attempt${campaign.max_attempts === 1 ? "" : "s"}`,
    `retry after ${campaign.retry_delay_minutes} min`,
    profileName ? `as ${profileName}` : "each customer's own business profile",
  ];

  return (
    <PageShell
      title={campaign.name}
      description={settings.join(" · ")}
      actions={<CampaignStatusBadge status={campaign.status} />}
    >
      <AutoRefresh active={campaign.status === "running"} intervalMs={3000} />
      {campaign.status_reason ? (
        <div
          role="alert"
          className="rounded-lg border border-warning/30 bg-warning-muted px-4 py-3 text-sm text-warning-muted-foreground"
        >
          <p className="font-medium">The dialer paused this campaign</p>
          <p className="mt-0.5">{campaign.status_reason}</p>
          <p className="mt-0.5">No attempts were used. Fix the problem, then resume.</p>
        </div>
      ) : null}
      <CampaignControls campaignId={campaign.id} status={campaign.status} />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        {tiles.map((tile) => (
          <Card key={tile.label}>
            <p className="text-xs text-muted-foreground">{tile.label}</p>
            <p className="mt-1 text-xl font-semibold text-foreground">{tile.value}</p>
          </Card>
        ))}
      </div>

      <Table>
        <THead>
          <TR>
            <TH>Customer</TH>
            <TH>Status</TH>
            <TH>Attempts</TH>
            <TH>Last result</TH>
            <TH>Next try</TH>
            <TH>
              <span className="sr-only">Call</span>
            </TH>
          </TR>
        </THead>
        <TBody>
          {campaign.contacts.map((contact) => (
            <TR key={contact.id}>
              <TD>
                <p className="font-medium text-foreground">{contact.customer_name}</p>
                <p className="text-xs text-muted-foreground">{formatPhone(contact.customer_phone)}</p>
              </TD>
              <TD>
                <ContactStatusBadge status={contact.status} />
              </TD>
              <TD>
                {contact.attempts} / {campaign.max_attempts}
              </TD>
              <TD>
                {contact.last_outcome
                  ? (OUTCOME_LABEL[contact.last_outcome] ?? formatStatusLabel(contact.last_outcome))
                  : "—"}
              </TD>
              <TD>{contact.status === "pending" ? formatDateTime(contact.next_attempt_at) : "—"}</TD>
              <TD>
                {contact.last_call_id ? (
                  <Link href={`/calls/${contact.last_call_id}`} className={LINK_CLASS}>
                    View call
                  </Link>
                ) : null}
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </PageShell>
  );
}

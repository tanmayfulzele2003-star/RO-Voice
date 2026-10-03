import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { CampaignForm } from "@/components/sections/CampaignForm";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { BusinessProfile, Customer } from "@/types/api";

export const metadata: Metadata = {
  title: "New campaign",
};

// The API pages customers 100 at a time; a campaign can pick from this many.
const MAX_CUSTOMERS = 1000;

export default async function NewCampaignPage() {
  const customers: Customer[] = [];
  let profiles: BusinessProfile[] = [];
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    profiles = await apiClient.listProfiles();
    for (let offset = 0; offset < MAX_CUSTOMERS; offset += 100) {
      const page = await apiClient.listCustomers({ limit: 100, offset });
      customers.push(...page.items);
      if (customers.length >= page.total) break;
    }
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load customers.";
  }

  return (
    <PageShell
      title="New campaign"
      description="Pick who to call and how many calls may run at once. The campaign starts as a draft."
    >
      {loadError ? (
        <ErrorState message={loadError} />
      ) : (
        <Card className="max-w-4xl">
          <CampaignForm
            customers={customers}
            profiles={profiles.map((p) => ({ id: p.id, name: p.name }))}
          />
        </Card>
      )}
    </PageShell>
  );
}

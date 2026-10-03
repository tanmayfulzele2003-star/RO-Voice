import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { CompaniesManager } from "@/components/sections/team/CompaniesManager";
import { ErrorState } from "@/components/ui/States";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { Me, PlatformOrganization } from "@/types/api";

export const metadata: Metadata = {
  title: "Companies",
  description: "The companies using this installation.",
};

export default async function PlatformPage() {
  let me: Me | null = null;
  let orgs: PlatformOrganization[] = [];
  let loadError: string | null = null;
  try {
    const api = await getServerApiClient();
    me = await api.getMe();
    orgs = await api.listPlatformOrganizations();
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load companies.";
  }
  return (
    <PageShell
      title="Companies"
      description="Every business using this installation. Each one has its own team, numbers, customers and calls."
    >
      {loadError || !me ? (
        <ErrorState message={loadError ?? "Failed to load companies."} />
      ) : (
        <CompaniesManager orgs={orgs} myOrgId={me.organization.id} />
      )}
    </PageShell>
  );
}

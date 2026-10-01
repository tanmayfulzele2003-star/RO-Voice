import Link from "next/link";
import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { DeleteProfileButton } from "@/components/sections/DeleteProfileButton";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { BusinessProfile } from "@/types/api";

export const metadata: Metadata = {
  title: "Business profiles",
  description: "Configure the calling agent for each business you run campaigns for.",
};

const LINK_CLASS =
  "text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

export default async function ProfilesPage() {
  let profiles: BusinessProfile[] = [];
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    profiles = await apiClient.listProfiles();
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load profiles.";
  }

  return (
    <PageShell
      title="Business profiles"
      description="Each profile sets who the agent represents, what it sells, and what it collects on a call. Assign a profile to a customer to use it."
      actions={
        <Link
          href="/profiles/new"
          className="inline-flex items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          New profile
        </Link>
      }
    >
      {loadError ? (
        <ErrorState message={loadError} />
      ) : profiles.length === 0 ? (
        <EmptyState title="No profiles yet" description="Create a profile for your business." />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {profiles.map((profile) => (
            <Card key={profile.id}>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold text-foreground">{profile.name}</h2>
                {profile.is_default ? <Badge tone="info">Default</Badge> : null}
                {profile.industry ? <Badge>{profile.industry}</Badge> : null}
              </div>
              <p className="text-sm text-muted-foreground">
                Agent persona: <span className="text-foreground">{profile.agent_name}</span>
                {profile.language ? ` · ${profile.language}` : " · matches customer's language"}
              </p>
              <p className="mt-2 text-sm text-foreground">{profile.call_objective}</p>
              <p className="mt-3 text-xs text-muted-foreground">
                Collects {profile.fields.length} item{profile.fields.length === 1 ? "" : "s"}:{" "}
                {profile.fields.map((f) => f.label).join(", ")}
              </p>
              <div className="mt-4 flex items-center gap-4">
                <Link href={`/profiles/${profile.id}/edit`} className={LINK_CLASS}>
                  Edit
                </Link>
                {profile.is_default ? null : (
                  <DeleteProfileButton profileId={profile.id} profileName={profile.name} />
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </PageShell>
  );
}

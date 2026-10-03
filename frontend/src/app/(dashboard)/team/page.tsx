import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { CompanyNameForm } from "@/components/sections/team/CompanyNameForm";
import { TeamManager } from "@/components/sections/team/TeamManager";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { Invite, Me, TeamUser } from "@/types/api";

export const metadata: Metadata = {
  title: "Team",
  description: "Who can use the dashboard, and what they can do.",
};

export default async function TeamPage() {
  let me: Me | null = null;
  let users: TeamUser[] = [];
  let invites: Invite[] = [];
  let loadError: string | null = null;
  try {
    const api = await getServerApiClient();
    me = await api.getMe();
    [users, invites] = await Promise.all([api.listUsers(), api.listInvites()]);
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load the team.";
  }

  return (
    <PageShell
      title="Team"
      description="Invite people from your company and choose what each of them can do."
    >
      {loadError || !me ? (
        <ErrorState message={loadError ?? "Failed to load the team."} />
      ) : (
        <>
          <Card>
            <CompanyNameForm name={me.organization.name} canEdit={me.role === "owner"} />
          </Card>
          <TeamManager me={me} users={users} invites={invites} />
        </>
      )}
    </PageShell>
  );
}

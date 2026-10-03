import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { PasswordForm } from "@/components/sections/team/PasswordForm";
import { ROLE_INFO } from "@/lib/roles";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { Me } from "@/types/api";

export const metadata: Metadata = { title: "Account" };

export default async function AccountPage() {
  let me: Me | null = null;
  try {
    me = await (await getServerApiClient()).getMe();
  } catch (err) {
    redirectIfUnauthenticated(err);
  }
  if (!me) {
    return (
      <PageShell title="Account">
        <ErrorState message="Failed to load your account." />
      </PageShell>
    );
  }
  return (
    <PageShell title="Account" description={`Signed in as ${me.username}.`}>
      <Card>
        <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-muted-foreground">Company</dt>
            <dd className="font-medium text-foreground">{me.organization.name}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Role</dt>
            <dd className="font-medium text-foreground">
              {ROLE_INFO[me.role].label}
              {me.is_platform_admin ? " · Platform admin" : ""}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">What you can do</dt>
            <dd className="text-foreground">{ROLE_INFO[me.role].description}</dd>
          </div>
        </dl>
      </Card>
      <Card>
        <h2 className="mb-4 text-base font-semibold text-foreground">Change password</h2>
        <PasswordForm />
      </Card>
    </PageShell>
  );
}

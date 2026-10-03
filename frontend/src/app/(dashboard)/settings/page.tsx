import Link from "next/link";
import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { GeminiSettingsCard } from "@/components/sections/setup/GeminiSettingsCard";
import { PublicUrlCard } from "@/components/sections/setup/PublicUrlCard";
import { TwilioSettingsCard } from "@/components/sections/setup/TwilioSettingsCard";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/States";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { Me, OrgSettingsView, SettingsView } from "@/types/api";

export const metadata: Metadata = {
  title: "Settings",
  description: "Twilio, Gemini and server connection settings.",
};

export default async function SettingsPage() {
  let me: Me | null = null;
  let org: OrgSettingsView | null = null;
  let platform: SettingsView | null = null;
  let loadError: string | null = null;
  try {
    const api = await getServerApiClient();
    me = await api.getMe();
    org = await api.getOrgSettings();
    if (me.is_platform_admin) platform = await api.getPlatformSettings();
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load settings.";
  }

  return (
    <PageShell
      title="Settings"
      description="Saved settings take effect right away and override the server's environment variables."
      actions={
        <Link
          href="/get-started"
          className="text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          Setup checklist
        </Link>
      }
    >
      {loadError || !org || !me ? (
        <ErrorState message={loadError ?? "Failed to load settings."} />
      ) : (
        <>
          <Card>
            <h2 className="text-base font-semibold text-foreground">Twilio for {me.organization.name}</h2>
            <p className="mb-4 text-sm text-muted-foreground">
              The account {me.organization.name}&apos;s calls go through.
            </p>
            <TwilioSettingsCard settings={org.settings} usesPlatform={org.uses_platform_twilio && org.platform_twilio_available} />
          </Card>
          {platform ? (
            <section aria-labelledby="platform-heading" className="flex flex-col gap-4">
              <div>
                <h2 id="platform-heading" className="text-lg font-semibold text-foreground">
                  Platform settings
                </h2>
                <p className="text-sm text-muted-foreground">
                  Shared by every company on this installation. Only platform admins see this.
                </p>
              </div>
              <Card>
                <h3 className="mb-4 text-base font-semibold text-foreground">Gemini</h3>
                <GeminiSettingsCard settings={platform} />
              </Card>
              <Card>
                <h3 className="mb-4 text-base font-semibold text-foreground">Public URL</h3>
                <PublicUrlCard settings={platform} />
              </Card>
              <Card>
                <h3 className="text-base font-semibold text-foreground">Fallback Twilio account</h3>
                <p className="mb-4 text-sm text-muted-foreground">
                  Used by companies that haven&apos;t connected their own Twilio account.
                </p>
                <TwilioSettingsCard settings={platform} scope="platform" />
              </Card>
            </section>
          ) : null}
        </>
      )}
    </PageShell>
  );
}

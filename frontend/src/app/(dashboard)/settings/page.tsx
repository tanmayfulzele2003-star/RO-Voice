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
import type { SettingsView } from "@/types/api";

export const metadata: Metadata = {
  title: "Settings",
  description: "Twilio, Gemini and server connection settings.",
};

export default async function SettingsPage() {
  let settings: SettingsView | null = null;
  let loadError: string | null = null;
  try {
    settings = await (await getServerApiClient()).getSettings();
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
      {loadError || !settings ? (
        <ErrorState message={loadError ?? "Failed to load settings."} />
      ) : (
        <>
          <Card>
            <h2 className="mb-4 text-base font-semibold text-foreground">Twilio</h2>
            <TwilioSettingsCard settings={settings} />
          </Card>
          <Card>
            <h2 className="mb-4 text-base font-semibold text-foreground">Gemini</h2>
            <GeminiSettingsCard settings={settings} />
          </Card>
          <Card>
            <h2 className="mb-4 text-base font-semibold text-foreground">Public URL</h2>
            <PublicUrlCard settings={settings} />
          </Card>
        </>
      )}
    </PageShell>
  );
}

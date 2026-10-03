import type { Metadata } from "next";
import { PageShell } from "@/components/layout/PageShell";
import { NumbersManager } from "@/components/sections/NumbersManager";
import { ErrorState } from "@/components/ui/States";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { BusinessProfile, PhoneNumber } from "@/types/api";

export const metadata: Metadata = {
  title: "Phone numbers",
  description: "The Twilio numbers the agent calls from and answers on.",
};

export default async function NumbersPage() {
  let numbers: PhoneNumber[] = [];
  let profiles: BusinessProfile[] = [];
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    [numbers, profiles] = await Promise.all([apiClient.listNumbers(), apiClient.listProfiles()]);
  } catch (err) {
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load phone numbers.";
  }

  return (
    <PageShell
      title="Phone numbers"
      description="Outbound calls take turns across a business's own numbers, then the shared pool. People who call a number reach that business's agent."
    >
      {loadError ? (
        <ErrorState message={loadError} />
      ) : (
        <NumbersManager
          numbers={numbers}
          profiles={profiles.map((p) => ({ id: p.id, name: p.name }))}
        />
      )}
    </PageShell>
  );
}

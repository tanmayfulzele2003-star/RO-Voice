import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageShell } from "@/components/layout/PageShell";
import { BrowserCall } from "@/components/sections/BrowserCall";
import { ErrorState } from "@/components/ui/States";
import { ApiError } from "@/lib/apiClient";
import { redirectIfUnauthenticated } from "@/lib/auth";
import { getServerApiClient } from "@/lib/serverApiClient";
import type { BusinessProfile, Customer } from "@/types/api";

export const metadata: Metadata = {
  title: "Browser call",
  description: "Two-way AI voice call through the browser microphone (WebRTC).",
};

export default async function BrowserCallPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let customer: Customer | null = null;
  let profiles: BusinessProfile[] = [];
  let loadError: string | null = null;

  try {
    const apiClient = await getServerApiClient();
    [customer, profiles] = await Promise.all([apiClient.getCustomer(id), apiClient.listProfiles()]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    redirectIfUnauthenticated(err);
    loadError = err instanceof ApiError ? err.message : "Failed to load customer.";
  }

  if (loadError || !customer) {
    return (
      <PageShell title="Browser call">
        <ErrorState message={loadError ?? "Failed to load customer."} />
      </PageShell>
    );
  }

  const profile =
    profiles.find((p) => p.id === customer.profile_id) ?? profiles.find((p) => p.is_default);

  return (
    <PageShell
      title={`Browser call · ${customer.name}`}
      description="The same AI calling agent as a phone call, through your microphone and speakers — for demos when the calling provider's free tier can't reach a number. Use headphones for best results."
    >
      <BrowserCall
        customerId={customer.id}
        customerName={customer.name}
        profileName={profile?.name ?? "the default profile"}
      />
    </PageShell>
  );
}
